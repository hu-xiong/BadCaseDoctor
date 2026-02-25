# agents/bug_management_agent.py
"""
Bug 管理 Agent
通过对话的方式管理 Bug 列表，支持以下操作：
- list: 查询 Bug 列表（可按状态、优先级筛选）
- create: 创建新 Bug
- update: 更新 Bug 信息
- delete: 删除 Bug
- assign: 分配 Bug 给成员
- change_status: 修改 Bug 状态
- search: 搜索 Bug
"""

import json
from typing import Optional, Dict, Any
from datetime import datetime
from .base import BaseAgent
from config import Config


class BugManagementAgent(BaseAgent):
    name = "bug_management"
    
    def __init__(self):
        pass
    
    def _get_db_models(self):
        """延迟导入避免循环依赖"""
        from app import db, Bug, User, Project
        return db, Bug, User, Project
    
    def handle(self, userId: str, action: str, **kwargs) -> Dict[str, Any]:
        """
        处理 Bug 管理操作
        
        Args:
            userId: 用户ID
            action: 操作类型 (list/create/update/delete/assign/change_status/search)
            **kwargs: 其他参数
        """
        try:
            if action == "list":
                return self._list_bugs(userId, **kwargs)
            elif action == "create":
                return self._create_bug(userId, **kwargs)
            elif action == "update":
                return self._update_bug(userId, **kwargs)
            elif action == "delete":
                return self._delete_bug(userId, **kwargs)
            elif action == "assign":
                return self._assign_bug(userId, **kwargs)
            elif action == "change_status":
                return self._change_bug_status(userId, **kwargs)
            elif action == "search":
                return self._search_bugs(userId, **kwargs)
            else:
                return {
                    "code": 400,
                    "message": f"不支持的操作类型: {action}",
                    "data": None
                }
        except Exception as e:
            return {
                "code": 500,
                "message": f"操作失败: {str(e)}",
                "data": None
            }
    
    def _list_bugs(self, userId: str, **kwargs) -> Dict[str, Any]:
        """查询 Bug 列表"""
        db, Bug, User, Project = self._get_db_models()
        
        project_id = kwargs.get('project_id')
        status = kwargs.get('status')
        priority = kwargs.get('priority')
        assignee_id = kwargs.get('assignee_id')
        
        try:
            query = Bug.query
            
            if project_id:
                query = query.filter_by(project_id=project_id)
            if status:
                query = query.filter_by(status=status)
            if priority:
                query = query.filter_by(priority=priority)
            if assignee_id:
                query = query.filter_by(assignee_id=assignee_id)
            
            bugs = query.order_by(Bug.created_at.desc()).all()
            
            bug_list = []
            for bug in bugs:
                bug_list.append({
                    'id': bug.id,
                    'title': bug.title,
                    'status': bug.status,
                    'priority': bug.priority,
                    'assignee_id': bug.assignee_id,
                    'created_at': bug.created_at.isoformat() if bug.created_at else None,
                    'updated_at': bug.updated_at.isoformat() if bug.updated_at else None
                })
            
            return {
                "code": 200,
                "message": "查询成功",
                "data": {
                    "bugs": bug_list,
                    "total": len(bug_list)
                }
            }
        except Exception as e:
            return {
                "code": 500,
                "message": f"查询失败: {str(e)}",
                "data": None
            }
    
    def _create_bug(self, userId: str, **kwargs) -> Dict[str, Any]:
        """创建新 Bug"""
        db, Bug, User, Project = self._get_db_models()
        
        project_id = kwargs.get('project_id')
        title = kwargs.get('title')
        description = kwargs.get('description', '')
        priority = kwargs.get('priority', 'medium')
        assignee_id = kwargs.get('assignee_id')
        plan_id = kwargs.get('plan_id')
        
        if not title:
            return {
                "code": 400,
                "message": "Bug 标题不能为空",
                "data": None
            }
        
        try:
            bug = Bug(
                title=title,
                description=description,
                status='new',
                priority=priority,
                project_id=project_id,
                creator_id=int(userId),
                assignee_id=assignee_id,
                plan_id=plan_id
            )
            
            db.session.add(bug)
            db.session.commit()
            
            return {
                "code": 200,
                "message": "Bug 创建成功",
                "data": {
                    'id': bug.id,
                    'title': bug.title,
                    'status': bug.status
                }
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"创建失败: {str(e)}",
                "data": None
            }
    
    def _update_bug(self, userId: str, **kwargs) -> Dict[str, Any]:
        """更新 Bug 信息"""
        db, Bug, User, Project = self._get_db_models()
        
        bug_id = kwargs.get('bug_id')
        updates = kwargs.get('updates', {})
        
        if not bug_id:
            return {
                "code": 400,
                "message": "Bug ID 不能为空",
                "data": None
            }
        
        try:
            bug = Bug.query.get(int(bug_id))
            if not bug:
                return {
                    "code": 404,
                    "message": "Bug 不存在",
                    "data": None
                }
            
            # 更新字段
            if 'title' in updates:
                bug.title = updates['title']
            if 'description' in updates:
                bug.description = updates['description']
            if 'priority' in updates:
                bug.priority = updates['priority']
            if 'assignee_id' in updates:
                bug.assignee_id = updates['assignee_id']
            
            bug.updated_at = datetime.now()
            db.session.commit()
            
            return {
                "code": 200,
                "message": "Bug 更新成功",
                "data": {
                    'id': bug.id,
                    'title': bug.title
                }
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"更新失败: {str(e)}",
                "data": None
            }
    
    def _delete_bug(self, userId: str, **kwargs) -> Dict[str, Any]:
        """删除 Bug"""
        db, Bug, User, Project = self._get_db_models()
        
        bug_id = kwargs.get('bug_id')
        
        if not bug_id:
            return {
                "code": 400,
                "message": "Bug ID 不能为空",
                "data": None
            }
        
        try:
            bug = Bug.query.get(int(bug_id))
            if not bug:
                return {
                    "code": 404,
                    "message": "Bug 不存在",
                    "data": None
                }
            
            db.session.delete(bug)
            db.session.commit()
            
            return {
                "code": 200,
                "message": "Bug 删除成功",
                "data": None
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"删除失败: {str(e)}",
                "data": None
            }
    
    def _assign_bug(self, userId: str, **kwargs) -> Dict[str, Any]:
        """分配 Bug"""
        db, Bug, User, Project = self._get_db_models()
        
        bug_id = kwargs.get('bug_id')
        assignee_id = kwargs.get('assignee_id')
        
        if not bug_id or not assignee_id:
            return {
                "code": 400,
                "message": "Bug ID 和分配人不能为空",
                "data": None
            }
        
        try:
            bug = Bug.query.get(int(bug_id))
            if not bug:
                return {
                    "code": 404,
                    "message": "Bug 不存在",
                    "data": None
                }
            
            bug.assignee_id = assignee_id
            bug.updated_at = datetime.now()
            db.session.commit()
            
            return {
                "code": 200,
                "message": f"Bug 已分配",
                "data": {
                    'bug_id': bug_id,
                    'assignee_id': assignee_id
                }
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"分配失败: {str(e)}",
                "data": None
            }
    
    def _change_bug_status(self, userId: str, **kwargs) -> Dict[str, Any]:
        """修改 Bug 状态"""
        db, Bug, User, Project = self._get_db_models()
        
        bug_id = kwargs.get('bug_id')
        new_status = kwargs.get('status')
        
        valid_statuses = ['new', 'assigned', 'in_progress', 'resolved', 'closed', 'reopened']
        
        if not bug_id or not new_status:
            return {
                "code": 400,
                "message": "Bug ID 和状态不能为空",
                "data": None
            }
        
        if new_status not in valid_statuses:
            return {
                "code": 400,
                "message": f"无效的状态，必须是: {', '.join(valid_statuses)}",
                "data": None
            }
        
        try:
            # 从数据库获取 Bug
            bug = Bug.query.get(int(bug_id))
            if not bug:
                return {
                    "code": 404,
                    "message": "Bug 不存在",
                    "data": None
                }
            
            # 更新状态
            bug.status = new_status
            bug.updated_at = datetime.now()
            db.session.commit()
            
            return {
                "code": 200,
                "message": f"Bug 状态已更新为: {new_status}",
                "data": {
                    "bug_id": bug_id,
                    "status": new_status,
                    "title": bug.title
                }
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"更新 Bug 状态失败: {str(e)}",
                "data": None
            }
    
    def _search_bugs(self, userId: str, **kwargs) -> Dict[str, Any]:
        """搜索 Bug"""
        db, Bug, User, Project = self._get_db_models()
        
        project_id = kwargs.get('project_id')
        keyword = kwargs.get('keyword', '')
        
        try:
            query = Bug.query
            
            if project_id:
                query = query.filter_by(project_id=project_id)
            
            if keyword:
                query = query.filter(
                    db.or_(
                        Bug.title.ilike(f'%{keyword}%'),
                        Bug.description.ilike(f'%{keyword}%')
                    )
                )
            
            bugs = query.order_by(Bug.created_at.desc()).limit(50).all()
            
            matched_bugs = []
            for bug in bugs:
                matched_bugs.append({
                    'id': bug.id,
                    'title': bug.title,
                    'status': bug.status,
                    'priority': bug.priority,
                    'assignee_id': bug.assignee_id,
                    'plan_id': bug.plan_id
                })
            
            return {
                "code": 200,
                "message": f"找到 {len(matched_bugs)} 个匹配的 Bug",
                "data": {
                    "bugs": matched_bugs,
                    "total": len(matched_bugs)
                }
            }
        except Exception as e:
            return {
                "code": 500,
                "message": f"搜索失败: {str(e)}",
                "data": None
            }
