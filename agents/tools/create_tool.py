"""
对话新增Bug/BadCase/计划工具
支持预览和确认流程，集成Text2SQL智能查询
"""
from typing import Dict, Any, List, Optional
from agents.tool_registry import BaseTool
from config import Config
import difflib
import json

# Text2SQL Agent
try:
    from .sqlcoder_agent import LLMBackend, get_cached_text2sql_agent
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
        self.text2sql = None
    
    @staticmethod
    def _coerce_bool(value, default: bool = False) -> bool:
        """统一解析 confirm（避免 JSON 里字符串 \"true\"/\"false\" 或大小写导致误落库）。"""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ('true', '1', 'yes', 'on', '是', '确认'):
                return True
            if s in ('false', '0', 'no', 'off', '否'):
                return False
            return default
        return bool(value)

    @staticmethod
    def _positive_plan_id_or_none(v: Any) -> Optional[int]:
        """仅接受正整数计划 ID；None/0/''/非法 → None（未计划）。"""
        if v is None or v == '':
            return None
        try:
            n = int(v)
            return n if n > 0 else None
        except (TypeError, ValueError):
            return None

    def _resolve_plan_id_for_copy(
        self,
        *,
        explicit_raw: Any,
        copy_source_id: Any,
        plan_from_copy: Any,
    ) -> Optional[int]:
        """
        复制创建时 plan_id：显式正整数优先；否则沿用源的归属计划。
        源为「未计划」时：只有显式正 plan_id 才归入计划，避免 LLM 把上下文里的迭代 plan_id 误塞进未计划副本。
        """
        explicit = self._positive_plan_id_or_none(explicit_raw)
        src = self._positive_plan_id_or_none(plan_from_copy)
        if copy_source_id and str(copy_source_id).strip():
            if src is None:
                return explicit
            return explicit if explicit is not None else src
        return explicit if explicit is not None else src

    def _ensure_text2sql(self):
        if not TEXT2SQL_AVAILABLE or self.text2sql is not None:
            return
        try:
            self.text2sql = get_cached_text2sql_agent(
                database_path='instance/badcase_doctor.db',
                llm_backend=LLMBackend.GLM_5.value,
                debug=False,
                execution_mode="direct",
            )
        except Exception as e:
            self.text2sql = None
            print(f"[CREATE] Text2SQL懒加载初始化失败: {e}")
    
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
        confirm = self._coerce_bool(confirm, default=False)
        print(f"[CREATE] 开始处理创建请求: target={target}, confirm={confirm}")
        
        progress_callback = kwargs.get("progress_callback")
        def _progress(msg: str):
            try:
                s = str(msg)
                if callable(progress_callback):
                    progress_callback(s)
            except Exception:
                pass
        
        _progress(f"初始化 create 参数… target={target}, confirm={confirm}")
        
        # 若指定了复制来源用例，跳过 Text2SQL「智能填充」：否则会只填少数字段，覆盖不全源用例属性
        copy_src_id = (fields or {}).get('copy_from_testcase_id') or (fields or {}).get('source_testcase_id')
        skip_smart = bool(copy_src_id and str(copy_src_id).strip())
        if skip_smart and natural_query:
            _progress("检测到 copy_from_testcase_id：跳过智能填充，改为从源用例全量合并字段")
        
        # 如果提供了自然语言描述，尝试智能填充字段（非「复制用例」场景）
        if natural_query and not skip_smart:
            self._ensure_text2sql()
            _progress("智能填充字段：开始…")
        if natural_query and self.text2sql and not skip_smart:
            smart_fields = await self._smart_fill_fields(target, natural_query, project_id)
            if smart_fields:
                if fields:
                    smart_fields.update(fields)  # 用户提供的字段优先
                fields = smart_fields
            _progress("智能填充字段：完成")
        
        if not fields or not project_id:
            _fk = list(fields.keys())[:24] if isinstance(fields, dict) else type(fields).__name__
            _nq = bool((natural_query or "").strip())
            print(
                f"[CREATE] 校验失败（将返回 error）: project_id={project_id!r} missing={not project_id}, "
                f"fields_truthy={bool(fields)} fields_key_count={len(fields) if isinstance(fields, dict) else 'n/a'} "
                f"fields_keys={_fk!r} natural_query_nonempty={_nq}"
            )
            _progress("create：缺少必要参数，直接失败")
            return {
                'success': False,
                'error': '缺少必要参数：fields或project_id'
            }

        # create 会被 react_simplified 放入线程池执行，线程里没有 Flask app context。
        # 为了保证复制/补全字段阶段能正常查询 TestCase 等表，这里给整个 execute 包一层 app_context。
        from app import app as flask_app
        with flask_app.app_context():
            try:
                _progress("检查相似记录：开始…")
                # 1. 查询相似记录（避免重复创建）
                similar_records = await self._check_similar_records(target, fields, project_id)
                _progress("检查相似记录：完成")
                
                _progress("验证与补全字段：开始…")
                # 2. 验证和补全字段
                validated_fields = self._validate_and_complete_fields(target, fields, project_id)
                _progress("验证与补全字段：完成")
                
                # 3. 如果用户确认，执行创建
                if confirm:
                    _progress("确认创建：开始落库…")
                    created_id = await self._create_record(target, validated_fields, project_id)
                    if created_id:
                        _progress("落库成功")
                        return {
                            'success': True,
                            'message': f'已成功创建{self._get_target_label(target)}',
                            'target': target,
                            'created_id': created_id,
                            'fields': validated_fields,
                            'similar_records': similar_records if similar_records else None
                        }
                    else:
                        _progress("落库失败")
                        return {
                            'success': False,
                            'error': f'创建{self._get_target_label(target)}失败'
                        }
                
                # 4. 返回预览（需要用户确认）
                # 生成新增的 diff（全部为 add 类型，暗绿色表示新增）
                _progress("生成 diff 预览：开始…")
                diff_result = self._generate_create_diff(target, validated_fields)
                _progress("生成 diff 预览：完成")
                _progress("新建预览就绪，等待用户确认")
                
                return {
                    'success': True,
                    'confirmation_required': True,
                    'message': f'请确认以下{self._get_target_label(target)}信息：',
                    'target': target,
                    'preview': validated_fields,
                    'diff': diff_result,  # 新增 diff 字段
                    'similar_records': similar_records if similar_records else None
                }
                
            except Exception as e:
                print(f"[CREATE] 错误: {e}")
                _progress(f"create：失败：{e}")
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
        """验证 Bug 字段"""
        # 检查是否是复制场景
        copy_from_bug_id = fields.get('copy_from_bug_id') or fields.get('source_bug_id')
        plan_from_copy = None
            
        # 如果是复制 Bug，获取源 Bug 的 plan_id
        src_bug = None
        if copy_from_bug_id:
            from app import Bug
            src_bug = self.db.query(Bug).get(int(copy_from_bug_id)) if copy_from_bug_id else None
            if src_bug:
                plan_from_copy = src_bug.plan_id
                print(f"[CREATE] copy_from_bug_id 命中：copy_from={copy_from_bug_id}, src_plan_id={plan_from_copy}")

        plan_id = self._resolve_plan_id_for_copy(
            explicit_raw=fields.get('plan_id'),
            copy_source_id=copy_from_bug_id,
            plan_from_copy=plan_from_copy,
        )

        validated = {
            'title': fields.get('title', ''),
            'description': fields.get('description', ''),
            'priority': fields.get('priority', '中'),
            'severity': fields.get('severity', 'medium'),
            'status': fields.get('status', 'new'),
            'project_id': project_id,
            'plan_id': plan_id,
            'assignee_id': fields.get('assignee_id'),
            'reproduce_steps': fields.get('reproduce_steps', ''),
            'expected_result': fields.get('expected_result', ''),
            'actual_result': fields.get('actual_result', '')
        }
            
        if not validated['title']:
            raise ValueError('Bug 标题不能为空')
            
        return validated
    
    def _validate_badcase_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证 BadCase 字段"""
        # 检查是否是复制场景
        copy_from_badcase_id = fields.get('copy_from_badcase_id') or fields.get('source_badcase_id')
        plan_from_copy = None
            
        # 如果是复制 BadCase，获取源 BadCase 的 plan_id
        if copy_from_badcase_id:
            from app import BadCase
            src_badcase = self.db.query(BadCase).get(int(copy_from_badcase_id)) if copy_from_badcase_id else None
            if src_badcase:
                plan_from_copy = src_badcase.plan_id
                print(f"[CREATE] copy_from_badcase_id 命中：copy_from={copy_from_badcase_id}, src_plan_id={plan_from_copy}")

        plan_id = self._resolve_plan_id_for_copy(
            explicit_raw=fields.get('plan_id'),
            copy_source_id=copy_from_badcase_id,
            plan_from_copy=plan_from_copy,
        )

        validated = {
            'title': fields.get('title', ''),
            'description': fields.get('description', ''),
            'priority': fields.get('priority', '中'),
            'status': fields.get('status', '待处理'),
            'project_id': project_id,
            'plan_id': plan_id,
            'assignee_id': fields.get('assignee_id'),
            'reproduce_steps': fields.get('reproduce_steps', ''),
            'expected_result': fields.get('expected_result', ''),
            'actual_result': fields.get('actual_result', '')
        }
            
        if not validated['title']:
            raise ValueError('BadCase 标题不能为空')
            
        return validated
    
    def _validate_plan_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证迭代计划字段"""
        validated = {
            'name': fields.get('name', ''),
            'description': fields.get('description', ''),
            'status': fields.get('status', 'active'),
            'project_id': project_id,
            'parent_id': fields.get('parent_id'),
            'assignee_id': fields.get('assignee_id'),
            'start_date': fields.get('start_date'),
            'end_date': fields.get('end_date')
        }

        # 计划表字段已收敛：不再接收/使用“类型”字段。
        
        if not validated['name']:
            raise ValueError('计划名称不能为空')
        
        return validated
    
    def _validate_testcase_fields(self, fields: Dict, project_id: int) -> Dict:
        """
        验证测试用例字段。
        若带 copy_from_testcase_id：以源用例为基底全量复制业务字段（除 id/时间戳/最后执行时间），
        再用本次 fields 覆盖（通常为新标题）；validated 含 ORM 全部列，避免原先白名单遗漏。
        """
        from sqlalchemy.inspection import inspect as sa_inspect
        from app import app as flask_app
        from app import TestCase as _TC

        copy_from = fields.get('copy_from_testcase_id') or fields.get('source_testcase_id')
        use_copy = copy_from is not None and str(copy_from).strip() != ''
        meta_keys = {'copy_from_testcase_id', 'source_testcase_id', 'natural_query'}
        plan_from_copy = None
        merged: Dict[str, Any] = {}

        if use_copy:
            try:
                # react_simplified 会把 create 放到线程池执行，线程里需要显式推入 Flask app context
                with flask_app.app_context():
                    src = None
                    # 1) 优先按主键 id 查询
                    try:
                        src_id = int(copy_from)
                        src = self.db.query(_TC).get(src_id)
                    except Exception:
                        src = None

                    # 2) 若 id 不存在：按标题包含关键词查询
                    #    这样兼容用户把“测试用例7”当成标题的一部分（而非数据库主键 7）。
                    if not src:
                        keyword = str(copy_from).strip()
                        if keyword:
                            src = (
                                self.db.query(_TC)
                                .filter(_TC.project_id == int(project_id))
                                .filter(_TC.title.ilike(f'%{keyword}%'))
                                .first()
                            )

                    if src:
                        plan_from_copy = src.plan_id
                        src_d = src.to_dict() or {}
                        skip_from_src = {'id', 'created_at', 'updated_at', 'last_executed'}
                        for k, v in src_d.items():
                            if k in skip_from_src:
                                continue
                            merged[k] = v
                        print(
                            f"[CREATE] copy_from_testcase_id 命中: copy_from={copy_from}, "
                            f"src_id={getattr(src, 'id', None)}, src_project_id={getattr(src, 'project_id', None)}, "
                            f"src_title={getattr(src, 'title', None)}, "
                            f"assignee_id={src_d.get('assignee_id')}, plan_id={src_d.get('plan_id')}, "
                            f"has_preconditions={bool(src_d.get('preconditions'))}, "
                            f"steps_type={type(src_d.get('steps')).__name__}, "
                            f"steps_len={len(src_d.get('steps') or []) if isinstance(src_d.get('steps'), list) else 'na'}"
                        )
                    else:
                        print(
                            f"[CREATE] copy_from_testcase_id 未命中：copy_from={copy_from}, "
                            f"project_id={project_id}, fallback_keyword='{str(copy_from).strip()}'"
                        )
            except Exception as ex:
                print(f"[CREATE] 从源用例加载失败: {ex}")

        for k, v in (fields or {}).items():
            if k in meta_keys:
                continue
            if v is None:
                continue
            # 复制模式下：LLM/前端可能会带来大量“空值字段”，这些会覆盖源用例的非空字段。
            # 这里忽略空值，确保“除标题外其他属性都与源用例一致”。
            if use_copy:
                if v == '' or v == [] or v == {}:
                    continue
                if isinstance(v, str):
                    sv = v.strip()
                    # 常见占位符（防止未替换的 bracket 占位覆盖源内容）
                    if sv.startswith('[') and sv.endswith(']'):
                        continue
            merged[k] = v

        merged['project_id'] = int(project_id)
        merged['plan_id'] = self._resolve_plan_id_for_copy(
            explicit_raw=merged.get('plan_id'),
            copy_source_id=copy_from if use_copy else None,
            plan_from_copy=plan_from_copy,
        )

        if not use_copy:
            # 无复制源：补默认，避免 NOT NULL / 缺字段（与原先白名单行为一致）
            merged.setdefault('status', 'draft')
            merged.setdefault('case_type', '功能测试')
            merged.setdefault('priority', 'P3')
            merged.setdefault('test_type', '手动')
            merged.setdefault('preconditions', '')
            merged.setdefault('steps', [])
            merged.setdefault('remark', '')
            merged.setdefault('related_defects', [])
            merged.setdefault('baseline', '')
            merged.setdefault('estimated_time', 0)
            merged.setdefault('version', 'v1')

        if not merged.get('title'):
            raise ValueError('测试用例标题不能为空')

        allowed = {c.key for c in sa_inspect(_TC).mapper.column_attrs}
        validated = {k: merged[k] for k in allowed if k in merged}
        validated.pop('id', None)
        return validated
    
    async def _create_record(self, target: str, fields: Dict, project_id: int) -> int:
        """创建记录到数据库"""
        try:
            from app import app as flask_app
            # 剔除仅用于复制/预览的元数据字段，避免传入 ORM 构造器
            fields = {
                k: v for k, v in fields.items()
                if k not in (
                    'copy_from_testcase_id', 'source_testcase_id',
                    'copy_from_bug_id', 'source_bug_id',
                    'copy_from_badcase_id', 'source_badcase_id'
                )
            }
            # 线程池落库同样需要 Flask app context
            with flask_app.app_context():
                if target == 'bug':
                    from app import Bug, Card, CardType
                    bug = Bug(**fields)
                    self.db.add(bug)
                    self.db.commit()
                    self.db.refresh(bug)
                    # 卡片层适配：创建 Card 映射（source_type/source_id），并回写 bug.card_id（若列存在）
                    try:
                        card = Card(
                            title=getattr(bug, "title", "") or fields.get("title", ""),
                            type=CardType.BUG,
                            priority=getattr(bug, "priority", None) or fields.get("priority", "p3"),
                            assignee_id=getattr(bug, "assignee_id", None),
                            project_id=int(project_id),
                            creator_id=getattr(bug, "creator_id", None) or int(fields.get("creator_id") or 0) or 0,
                            plan_id=getattr(bug, "plan_id", None),
                            description=getattr(bug, "description", None) or fields.get("description"),
                            source_type="bug",
                            source_id=int(bug.id),
                        )
                        self.db.add(card)
                        self.db.commit()
                        self.db.refresh(card)
                        try:
                            setattr(bug, "card_id", int(card.id))
                            self.db.commit()
                        except Exception:
                            self.db.rollback()
                    except Exception:
                        self.db.rollback()
                    return bug.id
                
                elif target == 'badcase':
                    from app import BadCase, Card, CardType
                    badcase = BadCase(**fields)
                    self.db.add(badcase)
                    self.db.commit()
                    self.db.refresh(badcase)
                    # 卡片层适配：创建 Card 映射（source_type/source_id）
                    try:
                        card = Card(
                            title=getattr(badcase, "title", "") or fields.get("title", ""),
                            type=CardType.BADCASE,
                            priority=getattr(badcase, "priority", None) or fields.get("priority", "p3"),
                            assignee_id=None,
                            project_id=int(project_id),
                            creator_id=getattr(badcase, "creator_id", None) or int(fields.get("creator_id") or 0) or 0,
                            plan_id=getattr(badcase, "plan_id", None),
                            description=getattr(badcase, "base_problem", None) or fields.get("description"),
                            source_type="badcase",
                            source_id=int(badcase.id),
                        )
                        self.db.add(card)
                        self.db.commit()
                    except Exception:
                        self.db.rollback()
                    return badcase.id
                
                elif target == 'plan':
                    from app import Plan
                    plan = Plan(**fields)
                    self.db.add(plan)
                    self.db.commit()
                    self.db.refresh(plan)
                    return plan.id
                
                elif target == 'testcase':
                    from app import TestCase, Card, CardType
                    testcase = TestCase(**fields)
                    self.db.add(testcase)
                    self.db.commit()
                    self.db.refresh(testcase)
                    # 卡片层适配：创建 Card 映射（source_type/source_id）
                    try:
                        card = Card(
                            title=getattr(testcase, "title", "") or fields.get("title", ""),
                            type=CardType.TESTCASE,
                            priority=getattr(testcase, "priority", None) or fields.get("priority", "P3"),
                            assignee_id=getattr(testcase, "assignee_id", None),
                            project_id=int(project_id),
                            creator_id=getattr(testcase, "creator_id", None) or int(fields.get("creator_id") or 0) or 0,
                            plan_id=getattr(testcase, "plan_id", None),
                            description=getattr(testcase, "remark", None) or fields.get("description"),
                            source_type="testcase",
                            source_id=int(testcase.id),
                        )
                        self.db.add(card)
                        self.db.commit()
                    except Exception:
                        self.db.rollback()
                    return testcase.id
                
                return None
            
        except Exception as e:
            print(f"[CREATE] 创建记录失败: {e}")
            self.db.rollback()
            return None
    
    def _generate_create_diff(self, target: str, fields: Dict) -> List[Dict]:
        """
        生成新增记录的 diff（全部为 add 类型，暗绿色表示新增）
        
        Args:
            target: 目标类型（bug/badcase/plan/testcase）
            fields: 字段内容
            
        Returns:
            diff 列表，每个元素包含 field、field_label、lines
        """
        # 字段中文标签映射
        field_labels = {
            # 通用字段
            'title': '标题',
            'name': '名称',
            'description': '描述',
            'status': '状态',
            'priority': '优先级',
            'assignee_id': '负责人',
            'assignee': '负责人',
            'plan_id': '所属计划',
            # Bug 字段
            'severity': '严重程度',
            'reproduce_steps': '复现步骤',
            'steps_to_reproduce': '复现步骤',
            'expected_result': '期望结果',
            'actual_result': '实际结果',
            # BadCase 字段
            'reproduction_steps': '复现步骤',
            'answer': '答案',
            'correct_answer': '正确答案',
            'badcase_result': 'BadCase结果',
            'base_problem': '相似问题',
            'solution': '解决方式',
            'problem_reason': '问题原因',
            # TestCase 字段
            'case_type': '用例类型',
            'test_type': '测试类型',
            'preconditions': '前置条件',
            'steps': '测试步骤',
            'remark': '备注',
            'execution_result': '执行结果',
            'baseline': '基线',
            'estimated_time': '预估工时',
            'actual_time': '实际工时',
            'version': '版本',
            'related_defects': '关联缺陷',
            'creator_id': '创建人',
            'executed_by': '执行人',
            'requirement_id': '关联需求',
            'remaining_time': '剩余工时',
            # Plan 字段
            'start_date': '开始日期',
            'end_date': '结束日期',
        }
        
        # 需要跳过的系统字段
        skip_fields = {
            'id', 'project_id', 'creator_id', 'created_at', 'updated_at',
            'copy_from_testcase_id', 'source_testcase_id',
        }
        
        diff_result = []
        
        for field, value in fields.items():
            # 跳过系统字段
            if field in skip_fields:
                continue
            
            # 跳过空值
            if value is None or value == '' or value == []:
                continue
            
            # 处理值：转换为字符串
            if isinstance(value, list):
                # 列表类型（如 steps）转为 JSON 字符串
                value_str = json.dumps(value, ensure_ascii=False, indent=2)
            elif isinstance(value, dict):
                value_str = json.dumps(value, ensure_ascii=False, indent=2)
            else:
                value_str = str(value)
            
            # 为多行内容分割成多行
            lines = value_str.split('\n') if '\n' in value_str else [value_str]
            
            # 生成 diff 行（全部为 add 类型）
            parsed_lines = []
            for i, line in enumerate(lines):
                parsed_lines.append({
                    'type': 'add',  # 新增类型，前端显示为暗绿色
                    'content': line,
                    'line_no': i
                })
            
            diff_result.append({
                'field': field,
                'field_label': field_labels.get(field, field),
                'lines': parsed_lines
            })
        
        return diff_result
