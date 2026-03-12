# agents/tools/database_tool.py
"""
数据库查询工具
查询已有的 Bug、BadCase、历史记录等
支持 Text2SQL 自然语言查询
支持 Docker 沙箱执行模式
"""

import json
from typing import Dict, Any, List
from ..tool_registry import BaseTool

# Text2SQL Agent
try:
    from .sqlcoder_agent import Text2SQLAgent, LLMBackend, ExecutionMode
    TEXT2SQL_AVAILABLE = True
except ImportError:
    TEXT2SQL_AVAILABLE = False
    print("[DB_TOOL] ⚠️ Text2SQLAgent 未安装，使用传统查询模式")


class DatabaseTool(BaseTool):
    """数据库查询工具"""
    
    def __init__(self, llm, db_session, execution_mode: str = "direct"):
        """
        初始化数据库工具
        
        Args:
            llm: 语言模型实例
            db_session: SQLAlchemy 数据库会话
            execution_mode: 执行模式 (direct/sandbox/hybrid)
        """
        super().__init__(
            name='database_query',
            description='查询数据库获取 Bug列表、BadCase、历史记录等，支持自然语言查询和沙箱执行'
        )
        self.llm = llm
        self.db = db_session
        self.execution_mode = execution_mode
        
        # 初始化 Text2SQL Agent
        if TEXT2SQL_AVAILABLE:
            try:
                mode_enum = ExecutionMode(execution_mode)
                self.text2sql_agent = Text2SQLAgent(
                    database_path='instance/badcase_doctor.db',
                    llm_backend=LLMBackend.GLM_5,
                    debug=False,
                    execution_mode=mode_enum
                )
                print(f"[DB_TOOL] ✅ Text2SQL Agent 已启用 (执行模式: {execution_mode})")
            except Exception as e:
                self.text2sql_agent = None
                print(f"[DB_TOOL] ⚠️ Text2SQL Agent 初始化失败: {str(e)}")
        else:
            self.text2sql_agent = None
            print("[DB_TOOL] ⚠️ Text2SQL Agent 不可用，使用传统查询模式")
    
    async def execute(
        self,
        query_type: str = None,
        project_id: str = None,
        bug_id: str = None,
        keywords: str = None,
        plan_id: str = None,
        limit: int = 10,
        natural_query: str = None,
        sandbox_mode: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行数据库查询
        
        Args:
            query_type: 查询类型 (list_bugs/find_similar/get_history/search_pattern)
            project_id: 项目 ID
            bug_id: Bug ID
            keywords: 搜索关键词
            plan_id: 计划 ID
            limit: 返回数量限制
            natural_query: 自然语言查询（如："查询所有未解决的登录bug"）
            sandbox_mode: 沙箱执行模式 (direct/sandbox/hybrid)，覆盖默认设置
            **kwargs: 其他参数
            
        Returns:
            查询结果
        """
        # 决定执行模式
        exec_mode = sandbox_mode or self.execution_mode
        
        # 优先处理自然语言查询
        if natural_query and self.text2sql_agent:
            print(f"[DB_QUERY] 🗣️ 自然语言查询: {natural_query}")
            print(f"[DB_QUERY] 🔒 执行模式: {exec_mode}")
            return self._execute_natural_query(natural_query, project_id, exec_mode)
        
        # 传统查询逻辑
        if not query_type:
            query_type = kwargs.get('type') or kwargs.get('action') or kwargs.get('operation') or kwargs.get('query')
            
        if not query_type:
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
    
    def _execute_natural_query(self, natural_query: str, project_id: str = None, execution_mode: str = None) -> Dict[str, Any]:
        """
        执行自然语言查询
        
        Args:
            natural_query: 自然语言查询语句
            project_id: 项目ID（可选上下文）
            execution_mode: 执行模式 (direct/sandbox/hybrid)
            
        Returns:
            查询结果
        """
        try:
            # 添加上下文信息
            context = f"项目ID: {project_id}" if project_id else ""
            
            # 调用 Text2SQL Agent
            result = self.text2sql_agent.generate_sql(natural_query, context)
            
            if result['success']:
                # 决定执行模式
                exec_mode_enum = None
                if execution_mode:
                    try:
                        from .sqlcoder_agent import ExecutionMode
                        exec_mode_enum = ExecutionMode(execution_mode)
                    except:
                        pass
                
                # 执行SQL
                exec_result = self.text2sql_agent.execute_sql(
                    result['sql'], 
                    force_mode=exec_mode_enum
                )
                
                return {
                    'query_type': 'natural_language',
                    'natural_query': natural_query,
                    'generated_sql': result['sql'],
                    'results': exec_result.get('data', []),
                    'row_count': exec_result.get('row_count', 0),
                    'execution_mode': exec_result.get('execution_mode', execution_mode or 'direct'),
                    'success': True
                }
            else:
                return {
                    'error': result.get('error', 'SQL生成失败'),
                    'natural_query': natural_query,
                    'success': False
                }
                
        except Exception as e:
            print(f"[DB_QUERY] ❌ 自然语言查询失败: {str(e)}")
            return {
                'error': f'自然语言查询执行失败: {str(e)}',
                'natural_query': natural_query,
                'success': False
            }
    
    async def _list_bugs(self, project_id: str = None, plan_id: str = None, limit: int = 10, **kwargs) -> Dict[str, Any]:
        """获取 Bug 列表"""
        print(f"[DB_QUERY] 📋 列举Bug（项目: {project_id or 'all'}, 计划: {plan_id or 'all'}, 限制: {limit}）")
            
        try:
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
                
            if bug_id:
                original_bug = db.session.query(Bug).filter_by(id=bug_id).first()
                if not original_bug:
                    return {'error': f'Bug {bug_id} 不存在', 'success': False}
                keywords = original_bug.title
                
            if not keywords:
                url = kwargs.get('url', '')
                if 'login' in url.lower():
                    keywords = '登录'
                elif 'project-detail' in url.lower():
                    keywords = '项目 界面'
                elif 'bug' in url.lower():
                    keywords = 'bug 编辑'
                else:
                    keywords = '界面'
                print(f"[DB_QUERY] 🧐 从 URL 自动提取关键词: {keywords}")
                
            if not keywords:
                return {
                    'error': '查找相似Bug需要提供 keywords 参数或 bug_id 参数',
                    'success': False,
                    'hint': '例: {"query_type": "find_similar", "keywords": "登录失败"}'
                }
            
            query = db.session.query(Bug).filter(
                Bug.title.ilike(f'%{keywords}%')
            )
            
            if project_id:
                query = query.filter_by(project_id=project_id)
                
                if not plan_id:
                    bug_type_plans = db.session.query(Plan).filter_by(
                        project_id=project_id,
                        type='bug'
                    ).all()
                    if bug_type_plans:
                        bug_plan_ids = [p.id for p in bug_type_plans]
                        query = query.filter(Bug.plan_id.in_(bug_plan_ids))
            
            if plan_id:
                current_plan = db.session.query(Plan).filter_by(id=plan_id).first()
                if current_plan and current_plan.parent_id:
                    sibling_plans = db.session.query(Plan).filter_by(parent_id=current_plan.parent_id).all()
                    sibling_plan_ids = [p.id for p in sibling_plans]
                    query = query.filter(Bug.plan_id.in_(sibling_plan_ids))
                else:
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
            
            bugs = query.all()
            
            severity_stats = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
            status_stats = {'pending_review': 0, 'confirmed': 0, 'in_progress': 0, 'resolved': 0}
            
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
