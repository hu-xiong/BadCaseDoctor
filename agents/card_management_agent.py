# agents/card_management_agent.py
"""
卡片管理 Agent
通过对话的方式统一管理所有类型的卡片（Bug、BadCase、TestCase），支持以下操作：
- list: 查询卡片列表（可按类型、状态、优先级筛选）
- create: 创建新卡片
- update: 更新卡片信息
- delete: 删除卡片
- assign: 分配卡片给成员
- change_status: 修改卡片状态
- move: 移动卡片到计划
- search: 搜索卡片
- get_detail: 获取卡片详情
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from .base import BaseAgent
from config import Config


class CardManagementAgent(BaseAgent):
    """
    统一的卡片管理 Agent
    支持 Bug、BadCase、TestCase 三种类型的卡片管理
    """
    name = "card_management"
    
    def __init__(self):
        pass
    
    def _get_db_models(self):
        """延迟导入避免循环依赖"""
        from app import db, Card, CardType, CardStatus, User, Project, Plan
        return db, Card, CardType, CardStatus, User, Project, Plan
    
    def _get_source_models(self):
        """获取源表模型用于兼容"""
        from app import db, Bug, BadCase, TestCase
        return db, Bug, BadCase, TestCase
    
    def handle(self, userId: str, action: str, **kwargs) -> Dict[str, Any]:
        """
        处理卡片管理操作
        
        Args:
            userId: 用户ID
            action: 操作类型 (list/create/update/delete/assign/change_status/move/search/get_detail)
            **kwargs: 其他参数
        """
        try:
            if action == "list":
                return self._list_cards(userId, **kwargs)
            elif action == "create":
                return self._create_card(userId, **kwargs)
            elif action == "update":
                return self._update_card(userId, **kwargs)
            elif action == "delete":
                return self._delete_card(userId, **kwargs)
            elif action == "assign":
                return self._assign_card(userId, **kwargs)
            elif action == "change_status":
                return self._change_card_status(userId, **kwargs)
            elif action == "move":
                return self._move_card(userId, **kwargs)
            elif action == "search":
                return self._search_cards(userId, **kwargs)
            elif action == "get_detail":
                return self._get_card_detail(userId, **kwargs)
            elif action == "list_by_type":
                return self._list_cards_by_type(userId, **kwargs)
            else:
                return {
                    "code": 400,
                    "message": f"不支持的操作类型: {action}",
                    "data": None
                }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                "code": 500,
                "message": f"操作失败: {str(e)}",
                "data": None
            }
    
    def _card_to_dict(self, card) -> Dict[str, Any]:
        """将卡片对象转换为字典"""
        result = card.to_dict() if hasattr(card, 'to_dict') else {
            'id': card.id,
            'title': card.title,
            'type': card.type.value if hasattr(card.type, 'value') else card.type,
            'status': card.status.value if hasattr(card.status, 'value') else card.status,
            'priority': card.priority,
            'description': getattr(card, 'description', None),
            'project_id': card.project_id,
            'plan_id': getattr(card, 'plan_id', None),
            'assignee_id': getattr(card, 'assignee_id', None),
            'creator_id': card.creator_id,
            'created_at': card.created_at.isoformat() if card.created_at else None,
            'updated_at': card.updated_at.isoformat() if card.updated_at else None
        }
        
        # 添加负责人名称
        if hasattr(card, 'assignee') and card.assignee:
            result['assignee_name'] = card.assignee.name if hasattr(card.assignee, 'name') else str(card.assignee)
        
        # 添加计划名称
        if hasattr(card, 'plan') and card.plan:
            result['plan_name'] = card.plan.name
        
        return result
    
    def _list_cards(self, userId: str, **kwargs) -> Dict[str, Any]:
        """查询卡片列表（支持多类型）"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        project_id = kwargs.get('project_id')
        card_type = kwargs.get('type')  # bug, badcase, testcase
        status = kwargs.get('status')
        priority = kwargs.get('priority')
        assignee_id = kwargs.get('assignee_id')
        plan_id = kwargs.get('plan_id')
        include_unplanned = kwargs.get('include_unplanned', True)
        page = kwargs.get('page', 1)
        per_page = kwargs.get('per_page', 50)
        
        try:
            query = Card.query
            
            if project_id:
                query = query.filter(Card.project_id == project_id)
            
            if card_type:
                type_enum = getattr(CardType, card_type.upper(), None)
                if type_enum:
                    query = query.filter(Card.type == type_enum)
            
            if status:
                status_enum = getattr(CardStatus, status.upper(), None)
                if status_enum:
                    query = query.filter(Card.status == status_enum)
                else:
                    query = query.filter(Card.status == status)
            
            if priority:
                query = query.filter(Card.priority == priority)
            
            if assignee_id:
                query = query.filter(Card.assignee_id == assignee_id)
            
            if plan_id is not None:
                if plan_id == 'unplanned' or plan_id == '':
                    query = query.filter(Card.plan_id.is_(None))
                else:
                    query = query.filter(Card.plan_id == plan_id)
            
            # 排序
            query = query.order_by(Card.updated_at.desc())
            
            # 分页
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            
            cards = []
            for card in pagination.items:
                cards.append(self._card_to_dict(card))
            
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "cards": cards,
                    "pagination": {
                        "total": pagination.total,
                        "pages": pagination.pages,
                        "current_page": page,
                        "per_page": per_page
                    }
                }
            }
        except Exception as e:
            return {
                "code": 500,
                "message": f"查询卡片列表失败: {str(e)}",
                "data": None
            }
    
    def _create_card(self, userId: str, **kwargs) -> Dict[str, Any]:
        """创建卡片"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        project_id = kwargs.get('project_id')
        card_type = kwargs.get('type', 'badcase')
        title = kwargs.get('title')
        description = kwargs.get('description')
        priority = kwargs.get('priority', 'p3')
        assignee_id = kwargs.get('assignee_id')
        plan_id = kwargs.get('plan_id')
        
        # 类型特定字段
        severity = kwargs.get('severity')
        steps_to_reproduce = kwargs.get('steps_to_reproduce')
        expected_result = kwargs.get('expected_result')
        actual_result = kwargs.get('actual_result')
        case_category = kwargs.get('case_category')
        
        try:
            if not project_id or not title:
                return {
                    "code": 400,
                    "message": "缺少必填参数: project_id, title",
                    "data": None
                }
            
            # 验证项目
            project = Project.query.get(project_id)
            if not project:
                return {
                    "code": 404,
                    "message": "项目不存在",
                    "data": None
                }
            
            # 获取用户
            user = User.query.filter_by(id=userId).first()
            if not user:
                user = User.query.filter_by(email=userId).first()
            if not user:
                return {
                    "code": 404,
                    "message": "用户不存在",
                    "data": None
                }
            
            # 创建卡片
            type_enum = getattr(CardType, card_type.upper(), CardType.BADCASE)
            
            card = Card(
                title=title,
                type=type_enum,
                status=CardStatus.OPEN,
                priority=priority,
                description=description,
                project_id=project_id,
                creator_id=user.id,
                plan_id=plan_id if plan_id != 'unplanned' else None,
                assignee_id=assignee_id,
                source_type=None,  # 新创建的卡片
                source_id=None
            )
            
            # 根据类型添加特定字段
            if card_type == 'bug':
                card.severity = severity or 'medium'
                card.steps_to_reproduce = steps_to_reproduce
                card.expected_result = expected_result
                card.actual_result = actual_result
            elif card_type == 'badcase':
                card.case_category = case_category or '功能异常'
            
            db.session.add(card)
            db.session.commit()
            
            return {
                "code": 200,
                "message": "卡片创建成功",
                "data": self._card_to_dict(card)
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"创建卡片失败: {str(e)}",
                "data": None
            }
    
    def _update_card(self, userId: str, **kwargs) -> Dict[str, Any]:
        """更新卡片"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        card_id = kwargs.get('card_id')
        title = kwargs.get('title')
        description = kwargs.get('description')
        priority = kwargs.get('priority')
        assignee_id = kwargs.get('assignee_id')
        status = kwargs.get('status')
        
        try:
            card = Card.query.get(card_id)
            if not card:
                return {
                    "code": 404,
                    "message": "卡片不存在",
                    "data": None
                }
            
            # 更新字段
            if title:
                card.title = title
            if description is not None:
                card.description = description
            if priority:
                card.priority = priority
            if assignee_id is not None:
                card.assignee_id = assignee_id
            if status:
                status_enum = getattr(CardStatus, status.upper(), None)
                if status_enum:
                    card.status = status_enum
                else:
                    card.status = status
            
            card.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return {
                "code": 200,
                "message": "卡片更新成功",
                "data": self._card_to_dict(card)
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"更新卡片失败: {str(e)}",
                "data": None
            }
    
    def _delete_card(self, userId: str, **kwargs) -> Dict[str, Any]:
        """删除卡片"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        card_id = kwargs.get('card_id')
        
        try:
            card = Card.query.get(card_id)
            if not card:
                return {
                    "code": 404,
                    "message": "卡片不存在",
                    "data": None
                }
            
            db.session.delete(card)
            db.session.commit()
            
            return {
                "code": 200,
                "message": "卡片删除成功",
                "data": None
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"删除卡片失败: {str(e)}",
                "data": None
            }
    
    def _assign_card(self, userId: str, **kwargs) -> Dict[str, Any]:
        """分配卡片"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        card_id = kwargs.get('card_id')
        assignee_id = kwargs.get('assignee_id')
        
        try:
            card = Card.query.get(card_id)
            if not card:
                return {
                    "code": 404,
                    "message": "卡片不存在",
                    "data": None
                }
            
            # 验证负责人
            if assignee_id:
                assignee = User.query.get(assignee_id)
                if not assignee:
                    return {
                        "code": 404,
                        "message": "指定的负责人不存在",
                        "data": None
                    }
            
            card.assignee_id = assignee_id
            card.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return {
                "code": 200,
                "message": "卡片分配成功",
                "data": self._card_to_dict(card)
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"分配卡片失败: {str(e)}",
                "data": None
            }
    
    def _change_card_status(self, userId: str, **kwargs) -> Dict[str, Any]:
        """修改卡片状态"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        card_id = kwargs.get('card_id')
        new_status = kwargs.get('status')
        
        try:
            card = Card.query.get(card_id)
            if not card:
                return {
                    "code": 404,
                    "message": "卡片不存在",
                    "data": None
                }
            
            # 解析状态
            status_enum = getattr(CardStatus, new_status.upper(), None)
            if status_enum:
                card.status = status_enum
            else:
                # 尝试直接设置字符串
                card.status = new_status
            
            card.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return {
                "code": 200,
                "message": "状态修改成功",
                "data": self._card_to_dict(card)
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"修改状态失败: {str(e)}",
                "data": None
            }
    
    def _move_card(self, userId: str, **kwargs) -> Dict[str, Any]:
        """移动卡片到计划"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        card_id = kwargs.get('card_id')
        target_plan_id = kwargs.get('plan_id')  # None 表示移至未计划
        
        try:
            card = Card.query.get(card_id)
            if not card:
                return {
                    "code": 404,
                    "message": "卡片不存在",
                    "data": None
                }
            
            # 验证目标计划
            if target_plan_id is not None:
                plan = Plan.query.get(target_plan_id)
                if not plan:
                    return {
                        "code": 404,
                        "message": "目标计划不存在",
                        "data": None
                    }
                if plan.project_id != card.project_id:
                    return {
                        "code": 400,
                        "message": "目标计划不属于同一项目",
                        "data": None
                    }
            
            old_plan_id = card.plan_id
            card.plan_id = target_plan_id
            card.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return {
                "code": 200,
                "message": f"卡片已移动至{'计划 ' + str(target_plan_id) if target_plan_id else '未计划'}",
                "data": self._card_to_dict(card)
            }
        except Exception as e:
            db.session.rollback()
            return {
                "code": 500,
                "message": f"移动卡片失败: {str(e)}",
                "data": None
            }
    
    def _search_cards(self, userId: str, **kwargs) -> Dict[str, Any]:
        """搜索卡片"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        project_id = kwargs.get('project_id')
        query_text = kwargs.get('query', '').strip()
        card_types = kwargs.get('types', 'bug,badcase,testcase').split(',')
        page = kwargs.get('page', 1)
        per_page = kwargs.get('per_page', 20)
        
        try:
            if not query_text:
                return {
                    "code": 200,
                    "message": "success",
                    "data": {
                        "cards": [],
                        "pagination": {"total": 0, "pages": 0, "current_page": 1, "per_page": per_page}
                    }
                }
            
            query = Card.query
            
            if project_id:
                query = query.filter(Card.project_id == project_id)
            
            # 类型过滤
            type_enums = []
            for t in card_types:
                t = t.strip()
                type_enum = getattr(CardType, t.upper(), None)
                if type_enum:
                    type_enums.append(type_enum)
            
            if type_enums:
                query = query.filter(Card.type.in_(type_enums))
            
            # 搜索标题和描述
            search_pattern = f'%{query_text}%'
            query = query.filter(
                db.or_(
                    Card.title.ilike(search_pattern),
                    Card.description.ilike(search_pattern)
                )
            )
            
            # 统计各类型数量
            counts = {}
            for type_enum in type_enums:
                type_name = type_enum.value
                count = Card.query.filter(Card.type == type_enum)
                if project_id:
                    count = count.filter(Card.project_id == project_id)
                count = count.filter(
                    db.or_(
                        Card.title.ilike(search_pattern),
                        Card.description.ilike(search_pattern)
                    )
                ).count()
                counts[type_name] = count
            
            # 分页
            pagination = query.order_by(Card.updated_at.desc()).paginate(
                page=page, per_page=per_page, error_out=False
            )
            
            cards = []
            for card in pagination.items:
                cards.append(self._card_to_dict(card))
            
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "cards": cards,
                    "counts": counts,
                    "pagination": {
                        "total": pagination.total,
                        "pages": pagination.pages,
                        "current_page": page,
                        "per_page": per_page
                    }
                }
            }
        except Exception as e:
            return {
                "code": 500,
                "message": f"搜索卡片失败: {str(e)}",
                "data": None
            }
    
    def _get_card_detail(self, userId: str, **kwargs) -> Dict[str, Any]:
        """获取卡片详情"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        card_id = kwargs.get('card_id')
        
        try:
            card = Card.query.get(card_id)
            if not card:
                return {
                    "code": 404,
                    "message": "卡片不存在",
                    "data": None
                }
            
            return {
                "code": 200,
                "message": "success",
                "data": self._card_to_dict(card)
            }
        except Exception as e:
            return {
                "code": 500,
                "message": f"获取卡片详情失败: {str(e)}",
                "data": None
            }
    
    def _list_cards_by_type(self, userId: str, **kwargs) -> Dict[str, Any]:
        """按类型分别列出卡片（兼容旧接口）"""
        db, Card, CardType, CardStatus, User, Project, Plan = self._get_db_models()
        
        project_id = kwargs.get('project_id')
        
        try:
            result = {}
            
            for type_name in ['bug', 'badcase', 'testcase']:
                type_enum = getattr(CardType, type_name.upper(), None)
                if not type_enum:
                    continue
                
                query = Card.query.filter(Card.type == type_enum)
                if project_id:
                    query = query.filter(Card.project_id == project_id)
                
                cards = query.order_by(Card.updated_at.desc()).limit(100).all()
                result[type_name] = [self._card_to_dict(card) for card in cards]
            
            return {
                "code": 200,
                "message": "success",
                "data": result
            }
        except Exception as e:
            return {
                "code": 500,
                "message": f"查询卡片列表失败: {str(e)}",
                "data": None
            }
