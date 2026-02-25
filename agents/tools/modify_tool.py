"""
对话修改Bug/BadCase工具
支持行级别对比显示修改内容
"""
from typing import Dict, Any, List
from agents.tool_registry import BaseTool
from config import Config
import difflib


class ModifyTool(BaseTool):
    """对话修改Bug/BadCase工具"""
    
    def __init__(self, db_session):
        self.db = db_session
        self.name = "modify"
        self.description = """
用于修改Bug或BadCase的工具，支持对话式修改和行级别对比。

使用场景：
- 用户说"修改这个Bug的标题"
- 用户说"把优先级改成高"
- 用户说"更新复现步骤"

参数：
- target: 修改目标类型，'bug'或'badcase'
- target_id: 目标ID
- modifications: 修改内容字典，格式 {"字段名": "新值"}
- project_id: 项目ID（必需）

返回：
- before: 修改前的数据
- after: 修改后的数据
- diff: 行级别差异对比（红色删除，绿色新增）
- confirmation_required: 是否需要用户确认
"""
    
    def _get_app_context(self):
        """获取 Flask 应用上下文"""
        from app import app
        return app.app_context()
    
    def _normalize_status(self, status_value: str, target: str) -> str:
        """
        将中文状态描述映射到数据库定义的英文状态值
        
        Bug 状态: new, assigned, in_progress, resolved, closed, reopened
        BadCase 状态: new, pending, resolved, hold, reopen, close
        """
        status_value = str(status_value).strip().lower()
        
        # Bug 状态映射
        bug_status_map = {
            '新建': 'new',
            '新': 'new',
            '已分配': 'assigned',
            '分配': 'assigned',
            '进行中': 'in_progress',
            '处理中': 'in_progress',
            '已解决': 'resolved',
            '解决': 'resolved',
            '已关闭': 'closed',
            '关闭': 'closed',
            '已重新打开': 'reopened',
            '重新打开': 'reopened',
            '重开': 'reopened',
        }
        
        # BadCase 状态映射
        badcase_status_map = {
            '新建': 'new',
            '新': 'new',
            '待处理': 'pending',
            '等待': 'pending',
            '已解决': 'resolved',
            '解决': 'resolved',
            '搁置': 'hold',
            '暂停': 'hold',
            '已重新打开': 'reopen',
            '重新打开': 'reopen',
            '重开': 'reopen',
            '已关闭': 'close',
            '关闭': 'close',
        }
        
        # 如果已经是合法的英文状态值，直接返回
        bug_valid_status = ['new', 'assigned', 'in_progress', 'resolved', 'closed', 'reopened']
        badcase_valid_status = ['new', 'pending', 'resolved', 'hold', 'reopen', 'close']
        
        if target == 'bug':
            if status_value in bug_valid_status:
                return status_value
            return bug_status_map.get(status_value, status_value)
        else:  # badcase
            if status_value in badcase_valid_status:
                return status_value
            return badcase_status_map.get(status_value, status_value)
    
    async def execute(
        self,
        target: str = "bug",  # bug/badcase
        target_id: int = None,
        modifications: Dict[str, Any] = None,
        project_id: int = None,
        confirm: bool = True,  # 默认直接确认修改
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行修改操作
        
        Args:
            target: 修改目标类型（bug/badcase）
            target_id: 目标ID
            modifications: 修改内容
            project_id: 项目ID
            confirm: 是否直接应用修改
        """
        # 确保 target_id 是整数
        if target_id:
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                print(f"[MODIFY] target_id 转换失败: {target_id}")
                return {
                    'success': False,
                    'error': f'target_id 格式错误: {target_id}'
                }
        
        print(f"[MODIFY] 开始处理修改请求: target={target}, target_id={target_id}, modifications={modifications}, project_id={project_id}")
        
        if not target_id or not modifications:
            print(f"[MODIFY] 参数校验失败: target_id={target_id}, modifications={modifications}")
            return {
                'success': False,
                'error': f'缺少必要参数：target_id={target_id}或modifications={modifications}'
            }
        
        # 🔧 状态值映射：将中文状态描述映射到数据库定义的英文状态值
        if 'status' in modifications:
            modifications['status'] = self._normalize_status(modifications['status'], target)
        
        try:
            # 使用 Flask 应用上下文
            with self._get_app_context():
                # 1. 获取原始数据
                original_data = await self._get_original_data(target, target_id, project_id)
                if not original_data:
                    return {
                        'success': False,
                        'error': f'未找到{target} ID={target_id}'
                    }
                
                # 2. 生成修改后的数据
                modified_data = original_data.copy()
                modified_data.update(modifications)
                
                # 3. 生成行级别差异对比
                diff_result = self._generate_line_diff(original_data, modified_data, modifications.keys())
                
                # 4. 如果用户确认，执行修改
                if confirm:
                    success = await self._apply_modifications(target, target_id, modifications, project_id)
                    return {
                        'success': success,
                        'message': f'已成功修改{target} ID={target_id}',
                        'before': original_data,
                        'after': modified_data,
                        'diff': diff_result
                    }
                
                # 5. 返回预览（需要用户确认）
                return {
                    'success': True,
                    'confirmation_required': True,
                    'message': f'请确认以下修改：',
                    'target': target,
                    'target_id': target_id,
                    'before': original_data,
                    'after': modified_data,
                    'diff': diff_result,
                    'modifications': modifications
                }
            
        except Exception as e:
            print(f"[MODIFY] 错误: {e}")
            return {
                'success': False,
                'error': f'修改失败: {str(e)}'
            }
    
    async def _get_original_data(self, target: str, target_id: int, project_id: int) -> Dict[str, Any]:
        """获取原始数据"""
        if target == 'bug':
            from app import Bug
            bug = self.db.query(Bug).filter(
                Bug.id == target_id,
                Bug.project_id == project_id
            ).first()
            
            if not bug:
                return None
            
            return {
                'id': bug.id,
                'title': bug.title,
                'description': bug.description or '',
                'status': bug.status,
                'priority': bug.priority,
                'severity': bug.severity or '',
                'assignee_id': bug.assignee_id,
                'steps_to_reproduce': bug.steps_to_reproduce or '',
                'expected_result': bug.expected_result or '',
                'actual_result': bug.actual_result or ''
            }
        
        elif target == 'badcase':
            from app import BadCase
            badcase = self.db.query(BadCase).filter(
                BadCase.id == target_id,
                BadCase.project_id == project_id
            ).first()
            
            if not badcase:
                return None
            
            return {
                'id': badcase.id,
                'title': badcase.title,
                'status': badcase.status,
                'priority': badcase.priority,
                'assignee': badcase.assignee or '',
                'reproduction_steps': badcase.reproduction_steps or '',
                'correct_answer': badcase.correct_answer or '',
                'badcase_result': badcase.badcase_result or ''
            }
        
        return None
    
    def _generate_line_diff(self, before: Dict, after: Dict, changed_fields: List[str]) -> List[Dict]:
        """
        生成行级别差异对比
        
        Returns:
            [
                {
                    'field': '字段名',
                    'field_label': '字段显示名',
                    'lines': [
                        {'type': 'delete', 'content': '旧内容', 'line_no': 1},
                        {'type': 'add', 'content': '新内容', 'line_no': 1},
                        {'type': 'unchanged', 'content': '相同内容', 'line_no': 2}
                    ]
                }
            ]
        """
        field_labels = {
            'title': '标题',
            'description': '描述',
            'status': '状态',
            'priority': '优先级',
            'severity': '严重程度',
            'reproduce_steps': '复现步骤',
            'expected_result': '预期结果',
            'actual_result': '实际结果',
            'assignee_id': '负责人'
        }
        
        diff_result = []
        
        for field in changed_fields:
            before_value = str(before.get(field, ''))
            after_value = str(after.get(field, ''))
            
            # 按行分割
            before_lines = before_value.split('\n') if before_value else ['']
            after_lines = after_value.split('\n') if after_value else ['']
            
            # 使用difflib生成差异
            differ = difflib.Differ()
            diff_lines = list(differ.compare(before_lines, after_lines))
            
            # 解析diff结果
            parsed_lines = []
            line_no = 0
            
            for line in diff_lines:
                if line.startswith('- '):
                    # 删除的行（红色）
                    parsed_lines.append({
                        'type': 'delete',
                        'content': line[2:],
                        'line_no': line_no
                    })
                elif line.startswith('+ '):
                    # 新增的行（绿色）
                    parsed_lines.append({
                        'type': 'add',
                        'content': line[2:],
                        'line_no': line_no
                    })
                    line_no += 1
                elif line.startswith('  '):
                    # 未改变的行（灰色）
                    parsed_lines.append({
                        'type': 'unchanged',
                        'content': line[2:],
                        'line_no': line_no
                    })
                    line_no += 1
            
            diff_result.append({
                'field': field,
                'field_label': field_labels.get(field, field),
                'lines': parsed_lines
            })
        
        return diff_result
    
    async def _apply_modifications(self, target: str, target_id: int, modifications: Dict, project_id: int) -> bool:
        """应用修改到数据库"""
        try:
            if target == 'bug':
                from app import Bug
                bug = self.db.query(Bug).filter(
                    Bug.id == target_id,
                    Bug.project_id == project_id
                ).first()
                
                if not bug:
                    return False
                
                for field, value in modifications.items():
                    if hasattr(bug, field):
                        setattr(bug, field, value)
                
                self.db.commit()
                return True
            
            elif target == 'badcase':
                from app import BadCase
                badcase = self.db.query(BadCase).filter(
                    BadCase.id == target_id,
                    BadCase.project_id == project_id
                ).first()
                
                if not badcase:
                    return False
                
                for field, value in modifications.items():
                    if hasattr(badcase, field):
                        setattr(badcase, field, value)
                
                self.db.commit()
                return True
            
            return False
            
        except Exception as e:
            print(f"[MODIFY] 应用修改失败: {e}")
            self.db.rollback()
            return False
