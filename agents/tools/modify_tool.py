"""
对话修改Bug/BadCase工具
支持行级别对比显示修改内容，集成Text2SQL智能查询
"""
from typing import Dict, Any, List, Optional
from agents.tool_registry import BaseTool
from config import Config
import difflib
import json

# Text2SQL Agent
try:
    from .sqlcoder_agent import Text2SQLAgent, LLMBackend
    TEXT2SQL_AVAILABLE = True
except ImportError:
    TEXT2SQL_AVAILABLE = False


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
- 用户说"修改最近创建的bug状态为已解决"

参数：
- target: 修改目标类型，'bug'或'badcase'
- target_id: 目标ID（可选，如果提供natural_query可自动查找）
- modifications: 修改内容字典，格式 {"字段名": "新值"}
- project_id: 项目ID（必需）
- natural_query: 自然语言查询（可选，用于查找目标记录）

返回：
- before: 修改前的数据
- after: 修改后的数据
- diff: 行级别差异对比（红色删除，绿色新增）
- confirmation_required: 是否需要用户确认
"""
        
        # 初始化 Text2SQL Agent
        if TEXT2SQL_AVAILABLE:
            try:
                self.text2sql = Text2SQLAgent(
                    database_path='instance/badcase_doctor.db',
                    llm_backend=LLMBackend.GLM_5,
                    debug=False
                )
            except Exception as e:
                self.text2sql = None
                print(f"[MODIFY] Text2SQL初始化失败: {e}")
        else:
            self.text2sql = None
    
    def _get_app_context(self):
        """获取 Flask 应用上下文"""
        from app import app
        return app.app_context()
    
    def _normalize_status(self, status_value: str, target: str) -> str:
        """将中文状态描述映射到数据库定义的英文状态值"""
        status_value = str(status_value).strip().lower()
        
        bug_status_map = {
            '新建': 'new', '新': 'new',
            '已分配': 'assigned', '分配': 'assigned',
            '进行中': 'in_progress', '处理中': 'in_progress',
            '已解决': 'resolved', '解决': 'resolved',
            '已关闭': 'closed', '关闭': 'closed',
            '已重新打开': 'reopened', '重新打开': 'reopened', '重开': 'reopened',
        }
        
        badcase_status_map = {
            '新建': 'new', '新': 'new',
            '待处理': 'pending', '等待': 'pending',
            '已解决': 'resolved', '解决': 'resolved',
            '搁置': 'hold', '暂停': 'hold',
            '已重新打开': 'reopened', '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '已关闭': 'closed', '关闭': 'closed', 'close': 'closed',
        }
        
        bug_valid_status = ['new', 'assigned', 'in_progress', 'resolved', 'closed', 'reopened']
        badcase_valid_status = ['new', 'pending', 'resolved', 'hold', 'reopened', 'closed', 'not_badcase']
        
        if target == 'bug':
            if status_value in bug_valid_status:
                return status_value
            return bug_status_map.get(status_value, status_value)
        else:
            if status_value in badcase_valid_status:
                return status_value
            return badcase_status_map.get(status_value, status_value)
    
    async def execute(
        self,
        target: str = "bug",
        target_id: int = None,
        modifications: Dict[str, Any] = None,
        project_id: int = None,
        confirm: bool = True,
        natural_query: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行修改操作
        
        流程：
        1. confirm=False: 沙箱副本预览修改效果
        2. confirm=True: 应用修改到生产库
        
        Args:
            target: 修改目标类型（bug/badcase）
            target_id: 目标ID（可选）
            modifications: 修改内容
            project_id: 项目ID
            confirm: True=应用到生产库, False=沙箱预览
            natural_query: 自然语言查询（用于查找目标记录）
        """
        # 如果没有target_id但有natural_query，尝试查找
        if not target_id and natural_query and self.text2sql:
            target_id = await self._find_target_by_query(target, natural_query, project_id)
            if target_id:
                print(f"[MODIFY] 通过自然语言查询找到目标ID: {target_id}")
        
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
        
        print(f"[MODIFY] 开始处理修改请求: target={target}, target_id={target_id}, modifications={modifications}, confirm={confirm}")
        
        if not target_id or not modifications:
            error_msg = f'缺少必要参数：target_id={target_id}或modifications={modifications}'
            hint_msg = '请先使用 grep 工具查询并定位目标记录，然后再使用 modify 工具修改。'
            if not target_id:
                hint_msg += f'\n\n示例流程：\n1. 使用 grep 工具查询 {target}：grep(target="{target}", project_id={project_id})\n2. 从 grep 结果中获取 target_id\n3. 使用 modify 工具修改：modify(target="{target}", target_id=<从grep获取的ID>, modifications={modifications})'
            print(f"[MODIFY] ❌ {error_msg}")
            print(f"[MODIFY] 💡 {hint_msg}")
            return {
                'success': False,
                'error': error_msg,
                'hint': hint_msg,
                'need_grep_first': True,  # 标记需要先执行 grep
                'suggested_action': 'grep',
                'suggested_params': {'target': target, 'project_id': project_id}
            }
        
        # 字段名映射（LLM 可能返回 owner，需要映射为 assignee）
        normalized_modifications = {}
        for field, value in modifications.items():
            mapped_field = self._map_field_name(field, target)
            if mapped_field != field:
                print(f"[MODIFY] 字段映射: '{field}' -> '{mapped_field}'")
            normalized_modifications[mapped_field] = value
        modifications = normalized_modifications
        
        # 状态值映射
        if 'status' in modifications:
            original_status = modifications['status']
            normalized_status = self._normalize_status(modifications['status'], target)
            modifications['status'] = normalized_status
            print(f"[MODIFY] 状态映射: '{original_status}' -> '{normalized_status}'")
        
        try:
            with self._get_app_context():
                # 1. 获取原始数据（生产库）
                original_data = await self._get_original_data(target, target_id, project_id)
                if not original_data:
                    return {
                        'success': False,
                        'error': f'未找到{target} ID={target_id}'
                    }
                
                # 2. 生成修改后的数据
                modified_data = original_data.copy()
                modified_data.update(modifications)
                
                # 特殊处理：如果修改的是 assignee 字段，同步更新 assignee_display
                if 'assignee' in modifications and target == 'badcase':
                    from app import User, db as flask_db
                    try:
                        new_assignee = modifications['assignee']
                        # 尝试将新值解析为用户ID并获取用户名
                        user_id = int(new_assignee)
                        user = flask_db.session.query(User).get(user_id)
                        if user:
                            modified_data['assignee_display'] = user.name
                        else:
                            modified_data['assignee_display'] = str(new_assignee)
                    except (ValueError, TypeError):
                        modified_data['assignee_display'] = str(new_assignee)
                
                # 3. 生成行级别差异对比
                diff_result = self._generate_line_diff(original_data, modified_data, modifications.keys())
                
                # 4. 根据 confirm 决定执行模式
                if not confirm:
                    # confirm=False: 沙箱副本预览
                    sandbox_result = await self._preview_in_sandbox(target, target_id, modifications, project_id)
                    
                    # 生成人类可读的摘要
                    target_name = 'Bug' if target == 'bug' else ('测试用例' if target == 'testcase' else 'BadCase')
                    mod_summary = '、'.join([f'{k}:{v}' for k, v in modifications.items()])
                    
                    return {
                        'success': True,
                        'confirmation_required': True,
                        'message': '沙箱预览完成，请确认是否应用修改：',
                        'summary': f'预览修改{target_name}(ID={target_id})：{mod_summary}',
                        'target': target,
                        'target_id': target_id,
                        'before': original_data,
                        'after': modified_data,
                        'diff': diff_result,
                        'modifications': modifications,
                        'sandbox_preview': sandbox_result
                    }
                
                # confirm=True: 应用到生产库
                success = await self._apply_modifications(target, target_id, modifications, project_id)
                
                # 生成人类可读的摘要
                target_name = 'Bug' if target == 'bug' else ('测试用例' if target == 'testcase' else 'BadCase')
                mod_summary = '、'.join([f'{k}:{v}' for k, v in modifications.items()])
                
                return {
                    'success': success,
                    'message': f'已成功修改{target} ID={target_id}',
                    'summary': f'已修改{target_name}(ID={target_id})：{mod_summary}',
                    'before': original_data,
                    'after': modified_data,
                    'diff': diff_result
                }
            
        except Exception as e:
            print(f"[MODIFY] 错误: {e}")
            return {
                'success': False,
                'error': f'修改失败: {str(e)}'
            }
    
    async def _find_target_by_query(self, target: str, natural_query: str, project_id: int) -> int:
        """使用自然语言查询查找目标记录ID"""
        if not self.text2sql:
            return None
        
        try:
            table_name = 'bug' if target == 'bug' else 'bad_case'
            
            sql_result = self.text2sql.generate_sql(
                f"查找{table_name}表中{natural_query}的记录ID",
                f"项目ID: {project_id}"
            )
            
            if sql_result.get('success'):
                exec_result = self.text2sql.execute_sql(sql_result['sql'])
                if exec_result.get('success') and exec_result.get('data'):
                    # 返回第一条记录的ID
                    first_record = exec_result['data'][0]
                    return first_record.get('id')
            
            return None
            
        except Exception as e:
            print(f"[MODIFY] 自然语言查询失败: {e}")
            return None
    
    async def _get_original_data(self, target: str, target_id: int, project_id: int) -> Dict[str, Any]:
        """获取原始数据"""
        # 优先使用 Text2SQL 查询
        if self.text2sql:
            try:
                table_name = 'bug' if target == 'bug' else 'bad_case'
                sql_result = self.text2sql.generate_sql(
                    f"查询{table_name}表中ID为{target_id}的记录",
                    f"项目ID: {project_id}"
                )
                
                if sql_result.get('success'):
                    exec_result = self.text2sql.execute_sql(sql_result['sql'])
                    if exec_result.get('success') and exec_result.get('data'):
                        data = exec_result['data'][0]
                        # 补充 assignee 用户名字段（Bug/TestCase 使用 assignee_id，BadCase 使用 assignee）
                        from app import User, db as flask_db
                        if 'assignee_id' in data and data['assignee_id']:
                            # Bug/TestCase: 从用户表获取用户名
                            user = flask_db.session.query(User).get(data['assignee_id'])
                            data['assignee'] = user.name if user else ''
                        elif 'assignee' in data and data.get('assignee'):
                            # BadCase: assignee 存储的是用户ID字符串，需要转换为用户名
                            from app import User
                            try:
                                user_id = int(data['assignee'])
                                user = flask_db.session.query(User).get(user_id)
                                if user:
                                    data['assignee_display'] = user.name
                                    data['assignee_id'] = str(user_id)  # 保存原始用户ID
                                else:
                                    data['assignee_display'] = str(data['assignee'])
                            except (ValueError, TypeError):
                                data['assignee_display'] = str(data['assignee'])
                        else:
                            data['assignee'] = data.get('assignee', '') or ''
                            data['assignee_display'] = '未指派'
                        return data
            except Exception as e:
                print(f"[MODIFY] Text2SQL查询失败，回退到ORM: {e}")
        
        # 回退到 ORM 查询（使用 Flask-SQLAlchemy 的 db.session）
        from app import db as flask_db
        
        if target == 'bug':
            from app import Bug, User
            bug = flask_db.session.query(Bug).filter(
                Bug.id == target_id,
                Bug.project_id == project_id
            ).first()
            
            if not bug:
                return None
            
            # 获取负责人用户名
            assignee_name = ''
            if bug.assignee_id:
                user = flask_db.session.query(User).get(bug.assignee_id)
                if user:
                    assignee_name = user.name
            
            return {
                'id': bug.id,
                'title': bug.title,
                'description': bug.description or '',
                'status': bug.status.value if hasattr(bug.status, 'value') else str(bug.status),
                'priority': bug.priority,
                'severity': bug.severity or '',
                'assignee_id': bug.assignee_id,
                'assignee': assignee_name,  # 添加用户名字段用于显示
                'plan_id': bug.plan_id,
                'steps_to_reproduce': bug.steps_to_reproduce or '',
                'expected_result': bug.expected_result or '',
                'actual_result': bug.actual_result or ''
            }
        
        elif target == 'badcase':
            from app import BadCase
            badcase = flask_db.session.query(BadCase).filter(
                BadCase.id == target_id,
                BadCase.project_id == project_id
            ).first()
            
            if not badcase:
                return None
            
            return {
                'id': badcase.id,
                'title': badcase.title,
                'status': badcase.status.value if hasattr(badcase.status, 'value') else str(badcase.status),
                'priority': badcase.priority,
                'assignee': badcase.assignee or '',
                'plan_id': badcase.plan_id,
                'reproduction_steps': badcase.reproduction_steps or '',
                'correct_answer': badcase.correct_answer or '',
                'badcase_result': badcase.badcase_result or '',
                'base_problem': badcase.base_problem or ''
            }
        
        elif target == 'testcase':
            from app import TestCase, User
            testcase = flask_db.session.query(TestCase).filter(
                TestCase.id == target_id,
                TestCase.project_id == project_id
            ).first()
            
            if not testcase:
                return None
            
            # 获取执行人用户名
            executed_by_name = ''
            if testcase.executed_by:
                user = flask_db.session.query(User).get(testcase.executed_by)
                if user:
                    executed_by_name = user.name
            
            return {
                'id': testcase.id,
                'title': testcase.title,
                'status': testcase.status.value if testcase.status else '',
                'case_type': testcase.case_type or '',
                'priority': testcase.priority or '',
                'test_type': testcase.test_type or '',
                'preconditions': testcase.preconditions or '',
                'steps': json.dumps(testcase.steps, ensure_ascii=False) if testcase.steps else '',
                'remark': testcase.remark or '',
                'execution_result': testcase.execution_result.value if testcase.execution_result else '',
                'executed_by': executed_by_name,
                'estimated_time': testcase.estimated_time or '',
                'actual_time': testcase.actual_time or '',
                'baseline': testcase.baseline or ''
            }
        
        return None
    
    def _generate_line_diff(self, before: Dict, after: Dict, changed_fields: List[str]) -> List[Dict]:
        """生成行级别差异对比"""
        # 不可修改的字段列表
        immutable_fields = {'id', 'type', 'project_id', 'created_at', 'updated_at', 'creator_id', 'plan_id'}
        
        field_labels = {
            'title': '标题',
            'description': '描述',
            'status': '状态',
            'priority': '优先级',
            'severity': '严重程度',
            'reproduce_steps': '复现步骤',
            'expected_result': '预期结果',
            'actual_result': '实际结果',
            'assignee_id': '负责人',
            'assignee': '负责人',
            'owner': '负责人',  # LLM 可能返回 owner
            # Bug 字段
            'steps_to_reproduce': '复现步骤',
            # BadCase 字段
            'reproduction_steps': '复现步骤',
            'correct_answer': '正确答案',
            'badcase_result': 'BadCase结果',
            'base_problem': '相似问题',
            # TestCase 字段
            'case_type': '用例类型',
            'test_type': '测试类型',
            'preconditions': '前置条件',
            'steps': '测试步骤',
            'remark': '备注',
            'execution_result': '执行结果',
            'executed_by': '执行人',
            'estimated_time': '预估工时',
            'actual_time': '实际工时',
            'baseline': '基线'
        }
        
        diff_result = []
        
        for field in changed_fields:
            # 跳过不可修改的字段
            if field in immutable_fields:
                print(f"[MODIFY] 跳过不可修改字段: {field}")
                continue
            
            # 特殊处理：对于 assignee 字段，优先使用 assignee_display
            if field == 'assignee' and 'assignee_display' in before:
                before_value = str(before.get('assignee_display', before.get(field, '')))
                after_value = str(after.get('assignee_display', after.get(field, '')))
            else:
                before_value = str(before.get(field, ''))
                after_value = str(after.get(field, ''))
            
            # 构造 diff 行
            parsed_lines = []
            
            # 即使值相同，也显示 delete → add 格式（用户期望看到完整的修改预览）
            if before_value == after_value:
                # 值相同，仍然显示为 delete → add 格式
                parsed_lines.append({
                    'type': 'delete',
                    'content': before_value,
                    'line_no': 0
                })
                parsed_lines.append({
                    'type': 'add',
                    'content': after_value,
                    'line_no': 0
                })
            else:
                # 值不同，使用 difflib 生成详细 diff
                before_lines = before_value.split('\n') if before_value else ['']
                after_lines = after_value.split('\n') if after_value else ['']
                
                differ = difflib.Differ()
                diff_lines = list(differ.compare(before_lines, after_lines))
                
                line_no = 0
                
                for line in diff_lines:
                    if line.startswith('- '):
                        parsed_lines.append({
                            'type': 'delete',
                            'content': line[2:],
                            'line_no': line_no
                        })
                    elif line.startswith('+ '):
                        parsed_lines.append({
                            'type': 'add',
                            'content': line[2:],
                            'line_no': line_no
                        })
                        line_no += 1
                    elif line.startswith('  '):
                        # 对于多行内容中的 unchanged 行，仍然保留
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
    
    async def _preview_in_sandbox(self, target: str, target_id: int, modifications: Dict, project_id: int) -> Dict[str, Any]:
        """
        在沙箱副本上预览修改效果
        
        流程：
        1. 创建数据库副本
        2. 在副本上执行 UPDATE SQL
        3. 返回预览结果（不修改生产库）
        """
        if not self.text2sql:
            return {
                'success': False,
                'error': 'Text2SQL Agent 未初始化'
            }
        
        # 不可修改的字段列表
        immutable_fields = {'id', 'type', 'project_id', 'created_at', 'updated_at', 'creator_id', 'plan_id'}
        
        try:
            table_name_map = {
                'bug': 'bug',
                'badcase': 'bad_case',
                'testcase': 'test_case'
            }
            table_name = table_name_map.get(target, 'bug')
            
            # 构建修改描述
            set_clauses = []
            for field, value in modifications.items():
                # 跳过不可修改的字段
                if field in immutable_fields:
                    print(f"[MODIFY-SANDBOX] 跳过不可修改字段: {field}")
                    continue
                
                actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                field_name = self._map_field_name(field, target)
                
                # 用户相关字段：解析用户名到用户ID（BadCase 除外，因为它的 assignee 是字符串）
                if field in ['assignee', '负责人', 'creator', '创建人'] and target != 'badcase':
                    resolved_value = self._resolve_user_value(actual_value, project_id)
                    if resolved_value != actual_value:
                        print(f"[MODIFY-SANDBOX] 用户解析: '{actual_value}' -> 用户ID={resolved_value}")
                        actual_value = resolved_value
                
                if isinstance(actual_value, str):
                    set_clauses.append(f"{field_name}改为'{actual_value}'")
                else:
                    set_clauses.append(f"{field_name}改为{actual_value}")
            
            modify_desc = "、".join(set_clauses)
            
            # 构建自然语言更新请求
            nl_query = f"更新{table_name}表中ID为{target_id}的记录，将{modify_desc}"
            context = f"项目ID: {project_id}"
            
            print(f"[MODIFY-SANDBOX] 沙箱预览: {nl_query}")
            
            # 生成 SQL
            sql_result = self.text2sql.generate_sql(nl_query, context)
            
            if not sql_result.get('success'):
                return {
                    'success': False,
                    'error': f'SQL生成失败: {sql_result.get("error")}'
                }
            
            sql = sql_result['sql']
            print(f"[MODIFY-SANDBOX] 生成的SQL: {sql}")
            
            # 使用沙箱执行器（操作数据库副本）
            from agents.tools.text2sql import get_sandbox_executor, SecurityConfig
            
            # 配置：启用数据库副本模式
            sandbox_config = SecurityConfig(
                db_use_copy=True,      # 使用数据库副本
                db_read_only=False,    # 副本可写
                timeout=15
            )
            # 启用本地回退，当 llm-sandbox 不可用时使用本地执行
            sandbox = get_sandbox_executor(security_config=sandbox_config, fallback_to_local=True)
            
            # 在沙箱副本上执行 UPDATE
            db_config = {
                'path': 'instance/badcase_doctor.db',
                'type': 'sqlite'
            }
            
            result = sandbox.execute_sql(sql, db_config, skip_security_check=True)
            
            print(f"[MODIFY-SANDBOX] 沙箱执行结果: success={result.get('success')}")
            
            return {
                'success': result.get('success', False),
                'sql': sql,
                'sandbox_mode': True,
                'message': '沙箱预览完成，确认后将应用到生产库',
                'execution_result': result
            }
            
        except Exception as e:
            print(f"[MODIFY-SANDBOX] 沙箱预览失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _apply_modifications(self, target: str, target_id: int, modifications: Dict, project_id: int) -> bool:
        """应用修改到数据库 - 使用 Text2SQL Agent 生成 SQL"""
        print(f"\n{'='*60}")
        print(f"[MODIFY] 🚀 开始执行修改")
        print(f"[MODIFY] 目标: {target}, ID: {target_id}")
        print(f"[MODIFY] 修改内容: {modifications}")
        print(f"{'='*60}")
        
        # 不可修改的字段列表
        immutable_fields = {'id', 'type', 'project_id', 'created_at', 'updated_at', 'creator_id', 'plan_id'}
        
        try:
            # 构建自然语言修改描述
            table_name_map = {
                'bug': 'bug',
                'badcase': 'bad_case',
                'testcase': 'test_case'
            }
            table_name = table_name_map.get(target, 'bug')
            
            # 解析后的修改内容（用于 ORM 回退）
            resolved_modifications = {}
            
            # 构建修改描述
            set_clauses = []
            for field, value in modifications.items():
                # 跳过不可修改的字段
                if field in immutable_fields:
                    print(f"[MODIFY] 跳过不可修改字段: {field}")
                    continue
                
                actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                # 字段名映射
                field_name = self._map_field_name(field, target)
                print(f"[MODIFY] 字段映射: '{field}' -> '{field_name}'")
                
                # 用户相关字段：解析用户名到用户ID
                # Bug/TestCase 使用 assignee_id（外键），BadCase 使用 assignee（字符串）
                if field in ['assignee', '负责人', 'creator', '创建人', 'owner']:
                    resolved_value = self._resolve_user_value(actual_value, project_id)
                    if resolved_value != actual_value:
                        print(f"[MODIFY] 用户解析: '{actual_value}' -> 用户ID={resolved_value}")
                        actual_value = resolved_value
                    # BadCase 的 assignee 存储字符串形式的用户ID
                    if target == 'badcase' and field in ['assignee', '负责人', 'owner']:
                        actual_value = str(actual_value)
                
                # 保存解析后的值
                resolved_modifications[field] = actual_value
                
                if isinstance(actual_value, str):
                    set_clauses.append(f"{field_name}改为'{actual_value}'")
                else:
                    set_clauses.append(f"{field_name}改为{actual_value}")
            
            modify_desc = "、".join(set_clauses)
            
            # 优先使用 Text2SQL 生成更新 SQL
            if self.text2sql:
                print(f"[MODIFY] ✅ Text2SQL Agent 可用，使用 Text2SQL 执行")
                try:
                    # 构建自然语言更新请求
                    nl_query = f"更新{table_name}表中ID为{target_id}的记录，将{modify_desc}"
                    context = f"项目ID: {project_id}"
                    
                    print(f"[MODIFY] 📝 自然语言请求: {nl_query}")
                    
                    # 生成 SQL
                    sql_result = self.text2sql.generate_sql(nl_query, context)
                    
                    if sql_result.get('success'):
                        sql = sql_result['sql']
                        print(f"[MODIFY] 🔧 生成的SQL: {sql}")
                        
                        # 检查 SQL 是否是 UPDATE 语句
                        if sql.strip().upper().startswith('UPDATE'):
                            # 直接执行 UPDATE（不经过沙箱，沙箱是只读的）
                            exec_result = self.text2sql.execute_sql(sql)
                            if exec_result.get('success'):
                                print(f"[MODIFY] ✅ 通过 Text2SQL 执行成功")
                                print(f"{'='*60}\n")
                                return True
                            else:
                                print(f"[MODIFY] ❌ Text2SQL执行失败: {exec_result.get('error')}")
                        else:
                            print(f"[MODIFY] ❌ Text2SQL生成的不是UPDATE语句: {sql}")
                    else:
                        print(f"[MODIFY] ❌ Text2SQL生成失败: {sql_result.get('error')}")
                        
                except Exception as e:
                    print(f"[MODIFY] ❌ Text2SQL处理异常: {e}")
            else:
                print(f"[MODIFY] ⚠️ Text2SQL Agent 不可用，回退到 ORM")
            
            # 回退到 ORM 方式
            print(f"[MODIFY] 🔄 回退到 ORM 方式执行")
            result = await self._apply_modifications_orm(target, target_id, resolved_modifications, project_id)
            print(f"{'='*60}\n")
            return result
            
        except Exception as e:
            print(f"[MODIFY] 应用修改失败: {e}")
            return False
    
    def _map_field_name(self, field: str, target: str) -> str:
        """字段名映射 - 将用户输入的字段名映射到数据库字段名"""
        # Bug 模型使用 assignee_id（外键）
        # BadCase 模型使用 assignee（字符串）
        # TestCase 模型使用 assignee_id（外键）
        
        # 通用映射：owner -> assignee
        common_mapping = {
            'owner': 'assignee',  # LLM 可能返回 owner
            '负责人': 'assignee',
        }
        
        if target == 'badcase':
            # BadCase 不需要映射 assignee，保持原字段名
            field_mapping = {
                **common_mapping,
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        else:
            # Bug 和 TestCase 使用 assignee_id
            field_mapping = {
                **common_mapping,
                'assignee': 'assignee_id',
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        
        if field in field_mapping:
            return field_mapping[field]
        return field
    
    def _resolve_user_value(self, value: Any, project_id: int = None) -> Any:
        """
        解析用户相关字段的值
        
        优先级：
        1. 先按用户名查询（无论是否数字）
        2. 找不到再尝试当ID用
        
        Args:
            value: 输入值（可能是用户名或用户ID）
            project_id: 项目ID（用于限定用户范围）
            
        Returns:
            用户ID（整数）
        """
        if isinstance(value, int):
            # 即使是整数，也先尝试按用户名查询
            str_value = str(value)
            user_id = self._find_user_by_name(str_value)
            if user_id:
                print(f"[MODIFY] 🔍 整数 '{value}' 匹配到用户名，返回用户ID={user_id}")
                return user_id
            # 没找到，直接返回原值作为ID
            return value
        
        if isinstance(value, str):
            # 先按用户名查询（优先级最高）
            user_id = self._find_user_by_name(value)
            if user_id:
                print(f"[MODIFY] ✅ 用户名 '{value}' -> 用户ID={user_id}")
                return user_id
            
            # 找不到用户，尝试解析为整数ID
            try:
                int_value = int(value)
                print(f"[MODIFY] ⚠️ 未找到用户名 '{value}'，尝试作为ID使用: {int_value}")
                return int_value
            except ValueError:
                pass
            
            print(f"[MODIFY] ❌ 无法解析用户: '{value}'")
            return value
        
        return value
    
    def _find_user_by_name(self, name: str) -> Optional[int]:
        """
        根据用户名查询用户ID
        
        Args:
            name: 用户名
            
        Returns:
            用户ID 或 None
        """
        try:
            from app import app, db, User
            with app.app_context():
                # 1. 精确匹配用户名
                user = User.query.filter(User.name == name).first()
                if user:
                    print(f"[MODIFY] 📌 精确匹配: User.name='{name}' -> id={user.id}")
                    return user.id
                
                # 2. 邮箱前缀匹配
                user = User.query.filter(User.email.ilike(f'{name}@%')).first()
                if user:
                    print(f"[MODIFY] 📧 邮箱匹配: email前缀='{name}' -> id={user.id}")
                    return user.id
                
                # 3. 模糊匹配用户名
                user = User.query.filter(User.name.ilike(f'%{name}%')).first()
                if user:
                    print(f"[MODIFY] 🔍 模糊匹配: name like '%{name}%' -> id={user.id}")
                    return user.id
                
                return None
                
        except Exception as e:
            print(f"[MODIFY] ❌ 查询用户失败: {e}")
            return None
    
    async def _apply_modifications_orm(self, target: str, target_id: int, modifications: Dict, project_id: int) -> bool:
        """ORM 方式应用修改（回退方案）
        
        注意：传入的 modifications 已经是解析后的值（用户名已转换为用户ID）
        """
        # Bug 和 TestCase 使用 assignee_id，BadCase 使用 assignee
        if target == 'badcase':
            field_mapping = {
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        else:
            field_mapping = {
                'assignee': 'assignee_id',
                '负责人': 'assignee_id',
                'creator': 'creator_id',
                '创建人': 'creator_id',
            }
        
        try:
            from app import db as flask_db
            
            if target == 'bug':
                from app import Bug
                bug = flask_db.session.query(Bug).filter(
                    Bug.id == target_id,
                    Bug.project_id == project_id
                ).first()
                
                if not bug:
                    return False
                
                for field, value in modifications.items():
                    # 应用字段映射
                    actual_field = field_mapping.get(field, field)
                    
                    if hasattr(bug, actual_field):
                        # 值已经在 _apply_modifications 中解析过了
                        actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                        
                        print(f"[MODIFY] 设置字段 {field} -> {actual_field} = {actual_value}")
                        setattr(bug, actual_field, actual_value)
                    else:
                        print(f"[MODIFY] 字段不存在: {field} (映射后: {actual_field})")
                
                flask_db.session.commit()
                return True
            
            elif target == 'badcase':
                from app import BadCase
                badcase = flask_db.session.query(BadCase).filter(
                    BadCase.id == target_id,
                    BadCase.project_id == project_id
                ).first()
                
                if not badcase:
                    return False
                
                for field, value in modifications.items():
                    # 应用字段映射
                    actual_field = field_mapping.get(field, field)
                    
                    if hasattr(badcase, actual_field):
                        # 值已经在 _apply_modifications 中解析过了
                        actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                        
                        print(f"[MODIFY] 设置字段 {field} -> {actual_field} = {actual_value}")
                        setattr(badcase, actual_field, actual_value)
                    else:
                        print(f"[MODIFY] 字段不存在: {field} (映射后: {actual_field})")
                
                flask_db.session.commit()
                return True
            
            elif target == 'testcase':
                from app import TestCase
                testcase = flask_db.session.query(TestCase).filter(
                    TestCase.id == target_id,
                    TestCase.project_id == project_id
                ).first()
                
                if not testcase:
                    return False
                
                for field, value in modifications.items():
                    # 应用字段映射
                    actual_field = field_mapping.get(field, field)
                    
                    if hasattr(testcase, actual_field):
                        # 值已经在 _apply_modifications 中解析过了
                        actual_value = value['new'] if isinstance(value, dict) and 'new' in value else value
                        
                        print(f"[MODIFY] 设置字段 {field} -> {actual_field} = {actual_value}")
                        setattr(testcase, actual_field, actual_value)
                    else:
                        print(f"[MODIFY] 字段不存在: {field} (映射后: {actual_field})")
                
                flask_db.session.commit()
                return True
            
            return False
            
        except Exception as e:
            print(f"[MODIFY] 应用修改失败: {e}")
            flask_db.session.rollback()
            return False
