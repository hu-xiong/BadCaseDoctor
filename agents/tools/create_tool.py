"""
对话新增Bug/BadCase/计划工具
支持预览和确认流程，集成Text2SQL智能查询
"""
from typing import Dict, Any
from agents.tool_registry import BaseTool
from config import Config

# Text2SQL Agent
try:
    from .sqlcoder_agent import Text2SQLAgent, LLMBackend
    TEXT2SQL_AVAILABLE = True
except ImportError:
    TEXT2SQL_AVAILABLE = False


class CreateTool(BaseTool):
    """对话新增Bug/BadCase/计划工具"""
    
    def __init__(self, db_session):
        self.db = db_session
        self.name = "create"
        self.description = """
用于新增Bug、BadCase或迭代计划的工具，支持对话式填充字段和预览确认。

使用场景：
- 用户说"创建一个登录相关的Bug"
- 用户说"新增一个优先级为高的BadCase"
- 用户说"创建一个新的迭代计划"

参数：
- target: 创建目标类型，'bug'、'badcase'、'plan'或'testcase'
- fields: 字段内容字典，如 {"title": "登录失败", "priority": "高"}
- project_id: 项目ID（必需）
- confirm: 是否直接确认创建（默认false，先预览）
- natural_query: 自然语言描述（可选，用于智能填充字段）

返回：
- preview: 预览数据（confirm=false时）
- created_id: 创建成功的ID（confirm=true时）
- confirmation_required: 是否需要用户确认
"""
        
        # 初始化 Text2SQL Agent
        if TEXT2SQL_AVAILABLE:
            try:
                self.text2sql = Text2SQLAgent(
                    database_path='instance/badcase_doctor.db',
                    llm_backend=LLMBackend.GLM_4_FLASH,
                    debug=False
                )
            except Exception as e:
                self.text2sql = None
                print(f"[CREATE] Text2SQL初始化失败: {e}")
        else:
            self.text2sql = None
    
    async def execute(
        self,
        target: str = "bug",
        fields: Dict[str, Any] = None,
        project_id: int = None,
        confirm: bool = False,
        natural_query: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行创建操作
        
        Args:
            target: 创建目标类型（bug/badcase/plan/testcase）
            fields: 字段内容
            project_id: 项目ID
            confirm: 是否直接创建
            natural_query: 自然语言描述
        """
        print(f"[CREATE] 开始处理创建请求: target={target}, confirm={confirm}")
        
        # 如果提供了自然语言描述，尝试智能填充字段
        if natural_query and self.text2sql:
            smart_fields = await self._smart_fill_fields(target, natural_query, project_id)
            if smart_fields:
                if fields:
                    smart_fields.update(fields)  # 用户提供的字段优先
                fields = smart_fields
        
        if not fields or not project_id:
            return {
                'success': False,
                'error': '缺少必要参数：fields或project_id'
            }
        
        try:
            # 1. 查询相似记录（避免重复创建）
            similar_records = await self._check_similar_records(target, fields, project_id)
            
            # 2. 验证和补全字段
            validated_fields = self._validate_and_complete_fields(target, fields, project_id)
            
            # 3. 如果用户确认，执行创建
            if confirm:
                created_id = await self._create_record(target, validated_fields, project_id)
                if created_id:
                    return {
                        'success': True,
                        'message': f'已成功创建{self._get_target_label(target)}',
                        'target': target,
                        'created_id': created_id,
                        'fields': validated_fields,
                        'similar_records': similar_records if similar_records else None
                    }
                else:
                    return {
                        'success': False,
                        'error': f'创建{self._get_target_label(target)}失败'
                    }
            
            # 4. 返回预览（需要用户确认）
            return {
                'success': True,
                'confirmation_required': True,
                'message': f'请确认以下{self._get_target_label(target)}信息：',
                'target': target,
                'preview': validated_fields,
                'similar_records': similar_records if similar_records else None
            }
            
        except Exception as e:
            print(f"[CREATE] 错误: {e}")
            return {
                'success': False,
                'error': f'创建失败: {str(e)}'
            }
    
    async def _smart_fill_fields(self, target: str, natural_query: str, project_id: int) -> Dict[str, Any]:
        """使用Text2SQL智能填充字段"""
        try:
            # 构建查询提示
            prompt = f"根据以下描述提取{target}的字段信息: {natural_query}"
            
            # 使用LLM提取字段（简化实现）
            if self.text2sql:
                # 查询相似记录作为参考
                sql_result = self.text2sql.generate_sql(
                    f"查询{target}表中与'{natural_query}'相关的记录",
                    f"项目ID: {project_id}"
                )
                if sql_result.get('success'):
                    exec_result = self.text2sql.execute_sql(sql_result['sql'])
                    if exec_result.get('success') and exec_result.get('data'):
                        # 参考相似记录的字段
                        ref = exec_result['data'][0]
                        return {
                            'title': natural_query,
                            'priority': ref.get('priority', '中'),
                        }
            
            return {'title': natural_query}
            
        except Exception as e:
            print(f"[CREATE] 智能填充失败: {e}")
            return {'title': natural_query}
    
    async def _check_similar_records(self, target: str, fields: Dict, project_id: int) -> list:
        """检查相似记录，避免重复创建"""
        if not self.text2sql:
            return []
        
        try:
            title = fields.get('title', '')
            if not title:
                return []
            
            table_name = 'bug' if target == 'bug' else 'bad_case' if target == 'badcase' else None
            if not table_name:
                return []
            
            sql_result = self.text2sql.generate_sql(
                f"查询{table_name}表中标题包含'{title}'的记录",
                f"项目ID: {project_id}"
            )
            
            if sql_result.get('success'):
                exec_result = self.text2sql.execute_sql(sql_result['sql'])
                if exec_result.get('success'):
                    return exec_result.get('data', [])[:3]  # 返回最多3条
            
            return []
            
        except Exception as e:
            print(f"[CREATE] 检查相似记录失败: {e}")
            return []
    
    def _get_target_label(self, target: str) -> str:
        """获取目标类型的中文标签"""
        labels = {
            'bug': 'Bug',
            'badcase': 'BadCase',
            'plan': '迭代计划',
            'testcase': '测试用例'
        }
        return labels.get(target, target)
    
    def _validate_and_complete_fields(self, target: str, fields: Dict, project_id: int) -> Dict:
        """验证和补全字段"""
        if target == 'bug':
            return self._validate_bug_fields(fields, project_id)
        elif target == 'badcase':
            return self._validate_badcase_fields(fields, project_id)
        elif target == 'plan':
            return self._validate_plan_fields(fields, project_id)
        elif target == 'testcase':
            return self._validate_testcase_fields(fields, project_id)
        else:
            raise ValueError(f"不支持的target类型: {target}")
    
    def _validate_bug_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证Bug字段"""
        validated = {
            'title': fields.get('title', ''),
            'description': fields.get('description', ''),
            'priority': fields.get('priority', '中'),
            'severity': fields.get('severity', 'medium'),
            'status': fields.get('status', 'new'),
            'project_id': project_id,
            'plan_id': fields.get('plan_id'),
            'assignee_id': fields.get('assignee_id'),
            'reproduce_steps': fields.get('reproduce_steps', ''),
            'expected_result': fields.get('expected_result', ''),
            'actual_result': fields.get('actual_result', '')
        }
        
        if not validated['title']:
            raise ValueError('Bug标题不能为空')
        
        return validated
    
    def _validate_badcase_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证BadCase字段"""
        validated = {
            'title': fields.get('title', ''),
            'description': fields.get('description', ''),
            'priority': fields.get('priority', '中'),
            'status': fields.get('status', '待处理'),
            'project_id': project_id,
            'plan_id': fields.get('plan_id'),
            'assignee_id': fields.get('assignee_id'),
            'reproduce_steps': fields.get('reproduce_steps', ''),
            'expected_result': fields.get('expected_result', ''),
            'actual_result': fields.get('actual_result', '')
        }
        
        if not validated['title']:
            raise ValueError('BadCase标题不能为空')
        
        return validated
    
    def _validate_plan_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证迭代计划字段"""
        validated = {
            'name': fields.get('name', ''),
            'description': fields.get('description', ''),
            'plan_type': fields.get('plan_type', 'bug'),
            'status': fields.get('status', 'active'),
            'project_id': project_id,
            'parent_id': fields.get('parent_id'),
            'assignee_id': fields.get('assignee_id'),
            'start_date': fields.get('start_date'),
            'end_date': fields.get('end_date')
        }
        
        if not validated['name']:
            raise ValueError('计划名称不能为空')
        
        return validated
    
    def _validate_testcase_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证测试用例字段"""
        validated = {
            'title': fields.get('title', ''),
            'status': fields.get('status', 'draft'),
            'case_type': fields.get('case_type', '功能测试'),
            'priority': fields.get('priority', 'P3'),
            'test_type': fields.get('test_type', '手动'),
            'preconditions': fields.get('preconditions', ''),
            'steps': fields.get('steps', []),
            'remark': fields.get('remark', ''),
            'project_id': project_id,
            'plan_id': fields.get('plan_id'),
            'assignee_id': fields.get('assignee_id'),
            'requirement_id': fields.get('requirement_id'),
            'related_defects': fields.get('related_defects', []),
            'baseline': fields.get('baseline', ''),
            'estimated_time': fields.get('estimated_time', 0),
            'version': fields.get('version', 'v1')
        }
        
        if not validated['title']:
            raise ValueError('测试用例标题不能为空')
        
        return validated
    
    async def _create_record(self, target: str, fields: Dict, project_id: int) -> int:
        """创建记录到数据库"""
        try:
            if target == 'bug':
                from app import Bug
                bug = Bug(**fields)
                self.db.add(bug)
                self.db.commit()
                self.db.refresh(bug)
                return bug.id
            
            elif target == 'badcase':
                from app import BadCase
                badcase = BadCase(**fields)
                self.db.add(badcase)
                self.db.commit()
                self.db.refresh(badcase)
                return badcase.id
            
            elif target == 'plan':
                from app import Plan
                plan = Plan(**fields)
                self.db.add(plan)
                self.db.commit()
                self.db.refresh(plan)
                return plan.id
            
            elif target == 'testcase':
                from app import TestCase
                testcase = TestCase(**fields)
                self.db.add(testcase)
                self.db.commit()
                self.db.refresh(testcase)
                return testcase.id
            
            return None
            
        except Exception as e:
            print(f"[CREATE] 创建记录失败: {e}")
            self.db.rollback()
            return None
