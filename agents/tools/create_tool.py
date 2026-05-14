"""
对话新增Bug/BadCase/计划工具
支持预览和确认流程，集成Text2SQL智能查询
"""
from typing import Dict, Any, List, Optional
from agents.tool_registry import BaseTool
from config import Config
import difflib
import json
import re

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

执行顺序（重要）：
1. 若 fields 中带 copy_from_bug_id / copy_from_testcase_id / copy_from_badcase_id（或由 natural_query 推断出复制源），
   服务端会先从数据库读出源记录，把业务字段全量合并进本次创建 payload，再用本次非空 fields 覆盖（通常为新标题）。
   这是「先复制属性、再创建」：合并发生在校验与预览阶段，不会在未确认时插入数据库。
2. confirm=false（默认）：只做校验与合并，返回 preview/diff，供用户在界面确认。
3. confirm=true：在合并后的字段上执行 INSERT，写入新记录。

使用场景：
- 用户说"创建一个登录相关的Bug"
- 用户说"复制某个Bug/用例新建，只改标题"
- 用户说"创建一个新的迭代计划"

参数：
- target: 创建目标类型，'bug'、'badcase'、'plan'、'testcase' 或 'card'（仅迭代卡片表 Card，不落 Bug/BadCase 源表）
- fields: 字段内容字典；复制时需 copy_from_*_id 或可推断的自然语言。
  target=card 时推荐 copy_from_card_id（或 source_card_id）：复制迭代列表里的另一条 Card，仅用标题/计划/类型等列表层字段；
  若要从底层 Bug/BadCase/TestCase 复制仍可用 copy_from_bug_id 等。
- project_id: 项目ID（必需）
- confirm: 是否直接确认创建（默认false，先预览）
- natural_query: 自然语言描述（可选；复制场景也会用来推断源标题/id）

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

    def _plan_id_for_bug_copy_merge(self, src_bug: Any) -> Any:
        """
        复制 Bug 时参与合并的「源计划」：**优先关联 Card.plan_id**（与迭代列表一致），
        再退回 Bug.plan_id。历史数据常有 Bug.plan_id=根迭代而 Card 在子迭代的情况。
        """
        if not src_bug:
            return None
        cid = getattr(src_bug, "card_id", None)
        if cid is not None and str(cid).strip() != "":
            try:
                from app import Card as _Card

                crow = self.db.query(_Card).get(int(cid))
                if crow is not None:
                    cp = getattr(crow, "plan_id", None)
                    if self._positive_plan_id_or_none(cp) is not None:
                        print(
                            f"[CREATE] copy Bug：沿用源 Card id={int(cid)} plan_id={cp} "
                            f"(Bug.plan_id={getattr(src_bug, 'plan_id', None)})"
                        )
                        return cp
            except Exception as ex:
                print(f"[CREATE] copy Bug：读取源 Card.plan_id 失败: {ex}")
        pid = getattr(src_bug, "plan_id", None)
        if self._positive_plan_id_or_none(pid) is not None:
            return pid
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
            if explicit is None:
                return src
            # 会话/旧 Bug 行上的 plan_id（如根迭代 1）常与源 Card 子迭代不一致；复制时以源 Card 推算的迭代为准
            if explicit != src:
                return src
            return explicit
        return explicit if explicit is not None else src

    def _infer_copy_bug_id_if_missing(
        self,
        fields: Dict[str, Any],
        natural_query: Optional[str],
        project_id: int,
    ) -> Optional[int]:
        """
        grep 未带回 first_bug_id、模型也未填 copy_from_bug_id 时，从用户话里抽「被复制的 Bug」标题片段，
        在当前项目下按标题模糊匹配，补全 copy_from_bug_id，使复制新建能合并源记录（预览不只标题+项目）。
        """
        raw = fields.get('copy_from_bug_id') or fields.get('source_bug_id')
        if raw is not None and str(raw).strip() != '':
            return None
        q = (natural_query or '').strip()

        # 优先：话里直接出现 Bug 数字 id（不要求「复制/拷贝」，避免模型改写用户话导致推断跳过）
        # 例：「复制 Bug1 新建…」「参照 bug #12」「Bug9 复制一份」
        try:
            from app import Bug as _Bug

            pid = int(project_id)
            # Bug/BUG 大写形式单独匹配，避免 debug123 误命中 bug 子串
            for pat in (
                r'(?:Bug|BUG)\s*[#＃]?\s*(\d+)',
                r'(?<![a-zA-Z])bug\s*[#＃]?\s*(\d+)',
            ):
                m = re.search(pat, q)
                if not m:
                    continue
                bid = int(m.group(1))
                row = self.db.query(_Bug).get(bid)
                if row and int(row.project_id or 0) == pid:
                    print(f"[CREATE] NL 推断复制源：按 Bug id 模式 {pat!r} -> id={bid} title={row.title!r}")
                    return bid
        except (TypeError, ValueError) as _ex:
            print(f"[CREATE] NL Bug id 模式解析跳过: {_ex}")

        if len(q) < 4:
            return None
        if not any(tok in q for tok in ('复制', '拷贝')):
            return None
        from app import Bug as _Bug

        candidates: List[str] = []
        # 复制一下登录bug1建一个新的… → 登录bug1
        m = re.search(r'复制\s*(?:一下|一个)?\s*([^\n建]+?)建', q)
        if m:
            candidates.append(m.group(1).strip())
        m2 = re.search(r'从\s*([^\s，。\n]{2,120}?)\s*(?:复制|拷贝)', q)
        if m2:
            candidates.append(m2.group(1).strip())
        m3 = re.search(r'(?:复制|拷贝)\s*Bug\s*[#＃]?\s*(\d+)', q, re.I)
        if m3:
            try:
                bid = int(m3.group(1))
                row = self.db.query(_Bug).get(bid)
                if row and int(row.project_id or 0) == int(project_id):
                    print(f"[CREATE] NL 推断复制源：按 Bug id={bid}")
                    return bid
            except (TypeError, ValueError):
                pass

        seen = set()
        pid = int(project_id)
        for phrase in candidates:
            phrase = phrase.strip().strip('，。、')
            if len(phrase) < 2 or phrase in seen:
                continue
            seen.add(phrase)
            rows = (
                self.db.query(_Bug)
                .filter(_Bug.project_id == pid)
                .filter(_Bug.title.ilike(f'%{phrase}%'))
                .order_by(_Bug.id.asc())
                .limit(8)
                .all()
            )
            if not rows:
                continue
            exact = [r for r in rows if (r.title or '').strip() == phrase]
            pick = exact[0] if exact else rows[0]
            print(f"[CREATE] NL 推断复制源：phrase={phrase!r} -> bug id={pick.id} title={pick.title!r}")
            return int(pick.id)
        return None

    def _enrich_preview_for_nav(
        self, target: str, preview: Dict[str, Any], original_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """预览中附带前端导航用的复制源 id（不落库、确认创建前应剔除）。"""
        out = dict(preview or {})
        of = original_fields or {}
        t = (target or "").strip().lower()
        try:
            if t == "bug":
                raw = of.get("copy_from_bug_id") or of.get("source_bug_id")
                if raw is not None and str(raw).strip():
                    try:
                        out["copy_from_bug_id"] = int(raw)
                    except (TypeError, ValueError):
                        pass
            elif t == "badcase":
                raw = of.get("copy_from_badcase_id") or of.get("source_badcase_id")
                if raw is not None and str(raw).strip():
                    try:
                        out["copy_from_badcase_id"] = int(raw)
                    except (TypeError, ValueError):
                        pass
            elif t == "testcase":
                raw = of.get("copy_from_testcase_id") or of.get("source_testcase_id")
                if raw is not None and str(raw).strip():
                    try:
                        out["copy_from_testcase_id"] = int(raw)
                    except (TypeError, ValueError):
                        pass
            elif t == "card":
                raw = of.get("copy_from_card_id") or of.get("source_card_id")
                if raw is not None and str(raw).strip():
                    try:
                        out["copy_from_card_id"] = int(raw)
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass
        try:
            self._attach_nav_copy_source_card(out, t)
        except Exception as _nav_ex:
            print(f"[CREATE] attach_nav_copy_source_card: {_nav_ex}")
        return out

    def _attach_nav_copy_source_card(self, out: Dict[str, Any], target_lower: str) -> None:
        """
        前端待确认行需定位「复制源」对应迭代卡片：补充 nav_copy_source_card_id（Card 主键）。
        copy 工具失败仅靠 create 兜底时，copy_from_* 仍在 fields 里则 out 已含源 id；此处再解析 Card 行。
        """
        t = (target_lower or "").strip().lower()
        try:
            if t == "bug":
                sid = out.get("copy_from_bug_id") or out.get("source_bug_id")
                if sid is None or str(sid).strip() == "":
                    return
                sid = int(sid)
                from app import Bug as _Bug
                from app import Card as _Card
                from app import CardType

                row = self.db.query(_Bug).get(sid)
                if row and getattr(row, "card_id", None):
                    out["nav_copy_source_card_id"] = int(row.card_id)
                else:
                    # Bug 未回填 card_id 时，按迭代卡片 source_id 反查（与老数据或迁移一致）
                    c = (
                        self.db.query(_Card)
                        .filter(_Card.source_id == sid)
                        .filter(_Card.type == CardType.BUG)
                        .first()
                    )
                    if c:
                        out["nav_copy_source_card_id"] = int(c.id)
            elif t == "badcase":
                sid = out.get("copy_from_badcase_id") or out.get("source_badcase_id")
                if sid is None or str(sid).strip() == "":
                    return
                sid = int(sid)
                from app import Card as _Card

                c = (
                    self.db.query(_Card)
                    .filter(_Card.source_id == sid)
                    .filter(_Card.source_type.in_(["badcase", "bad_case"]))
                    .first()
                )
                if c:
                    out["nav_copy_source_card_id"] = int(c.id)
            elif t == "testcase":
                sid = out.get("copy_from_testcase_id") or out.get("source_testcase_id")
                if sid is None or str(sid).strip() == "":
                    return
                sid = int(sid)
                from app import Card as _Card

                c = (
                    self.db.query(_Card)
                    .filter(_Card.source_id == sid)
                    .filter(_Card.source_type.in_(["testcase", "test_case"]))
                    .first()
                )
                if c:
                    out["nav_copy_source_card_id"] = int(c.id)
            elif t == "card":
                sid = out.get("copy_from_card_id") or out.get("source_card_id")
                if sid is not None and str(sid).strip() != "":
                    out["nav_copy_source_card_id"] = int(sid)
        except (TypeError, ValueError):
            pass

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
            target: 创建目标类型（bug/badcase/plan/testcase/card）
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
        
        # 若指定了复制来源（用例/Bug/BadCase），跳过 Text2SQL「智能填充」：否则会只填少数字段，冲掉源记录合并结果
        copy_tc = (fields or {}).get('copy_from_testcase_id') or (fields or {}).get('source_testcase_id')
        copy_bug = (fields or {}).get('copy_from_bug_id') or (fields or {}).get('source_bug_id')
        copy_bc = (fields or {}).get('copy_from_badcase_id') or (fields or {}).get('source_badcase_id')
        copy_card = (fields or {}).get('copy_from_card_id') or (fields or {}).get('source_card_id')

        def _copy_id_nonempty(v):
            return v is not None and str(v).strip() != ''

        skip_smart = (
            _copy_id_nonempty(copy_tc)
            or _copy_id_nonempty(copy_bug)
            or _copy_id_nonempty(copy_bc)
            or _copy_id_nonempty(copy_card)
        )
        if skip_smart and natural_query:
            _progress("检测到复制来源 id：跳过智能填充，改为从源记录全量合并字段")
        
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
                fields = dict(fields or {})
                if (target or '').strip().lower() == 'bug':
                    _bid = self._infer_copy_bug_id_if_missing(fields, natural_query, project_id)
                    if _bid is not None:
                        fields['copy_from_bug_id'] = _bid

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

                preview_out = self._enrich_preview_for_nav(target, validated_fields, fields)

                return {
                    'success': True,
                    'confirmation_required': True,
                    'message': f'请确认以下{self._get_target_label(target)}信息：',
                    'target': target,
                    'preview': preview_out,
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
            'testcase': '测试用例',
            'card': '卡片',
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
        elif target == 'card':
            return self._validate_card_fields(fields, project_id)
        else:
            raise ValueError(f"不支持的target类型: {target}")

    def _apply_minimal_copy_for_card(self, merged: Dict, project_id: int) -> None:
        """
        从 copy_from_* 源行只取「迭代列表上看得见的」信息：标题（可缺省回填）、计划、卡片类型。
        不合并 Bug 复现步骤、BadCase 答案、TestCase 步骤等详情列（那些属于点进详情后的源表数据）。
        优先 copy_from_card_id：迭代内复制另一条 Card，与 Card 主键对齐。
        """
        try:
            from app import Bug as _Bug, BadCase as _BC, TestCase as _TC, Card as _CardModel
        except Exception:
            return

        copy_card = merged.get('copy_from_card_id') or merged.get('source_card_id')
        if copy_card is not None and str(copy_card).strip() != '':
            try:
                src = self.db.query(_CardModel).get(int(copy_card))
                if src:
                    spid = int(getattr(src, 'project_id', 0) or 0)
                    if spid and spid != int(project_id):
                        print(
                            f"[CREATE] copy_from_card_id 项目不一致: card.project_id={spid} "
                            f"请求 project_id={project_id}"
                        )
                    if not str(merged.get('title') or '').strip():
                        merged['title'] = (getattr(src, 'title', None) or '').strip()
                    merged['plan_id'] = self._resolve_plan_id_for_copy(
                        explicit_raw=merged.get('plan_id'),
                        copy_source_id=copy_card,
                        plan_from_copy=getattr(src, 'plan_id', None),
                    )
                    ct = getattr(src, 'type', None)
                    if ct is not None:
                        merged['type'] = ct.value if hasattr(ct, 'value') else str(ct).lower()
                    if merged.get('priority') in (None, ''):
                        merged['priority'] = getattr(src, 'priority', None) or 'p3'
                    aid = getattr(src, 'assignee_id', None)
                    if merged.get('assignee_id') in (None, '') and aid is not None:
                        merged['assignee_id'] = aid
            except Exception as ex:
                print(f"[CREATE] card 复制源 Card id={copy_card} 失败: {ex}")
            return

        copy_bug = merged.get('copy_from_bug_id') or merged.get('source_bug_id')
        if copy_bug is not None and str(copy_bug).strip() != '':
            try:
                src = self.db.query(_Bug).get(int(copy_bug))
                if src:
                    if not str(merged.get('title') or '').strip():
                        merged['title'] = (getattr(src, 'title', None) or '').strip()
                    merged['plan_id'] = self._resolve_plan_id_for_copy(
                        explicit_raw=merged.get('plan_id'),
                        copy_source_id=copy_bug,
                        plan_from_copy=getattr(src, 'plan_id', None),
                    )
                    if not str(merged.get('type') or '').strip():
                        merged['type'] = 'bug'
            except Exception as ex:
                print(f"[CREATE] card 复制源 Bug 仅取标题/计划失败: {ex}")
            return

        copy_bc = merged.get('copy_from_badcase_id') or merged.get('source_badcase_id')
        if copy_bc is not None and str(copy_bc).strip() != '':
            try:
                src = self.db.query(_BC).get(int(copy_bc))
                if src:
                    if not str(merged.get('title') or '').strip():
                        merged['title'] = (getattr(src, 'title', None) or '').strip()
                    merged['plan_id'] = self._resolve_plan_id_for_copy(
                        explicit_raw=merged.get('plan_id'),
                        copy_source_id=copy_bc,
                        plan_from_copy=getattr(src, 'plan_id', None),
                    )
                    if not str(merged.get('type') or '').strip():
                        merged['type'] = 'badcase'
            except Exception as ex:
                print(f"[CREATE] card 复制源 BadCase 仅取标题/计划失败: {ex}")
            return

        copy_tc = merged.get('copy_from_testcase_id') or merged.get('source_testcase_id')
        if copy_tc is not None and str(copy_tc).strip() != '':
            try:
                src = self.db.query(_TC).get(int(copy_tc))
                if src:
                    if not str(merged.get('title') or '').strip():
                        merged['title'] = (getattr(src, 'title', None) or '').strip()
                    merged['plan_id'] = self._resolve_plan_id_for_copy(
                        explicit_raw=merged.get('plan_id'),
                        copy_source_id=copy_tc,
                        plan_from_copy=getattr(src, 'plan_id', None),
                    )
                    if not str(merged.get('type') or '').strip():
                        merged['type'] = 'testcase'
            except Exception as ex:
                print(f"[CREATE] card 复制源 TestCase 仅取标题/计划失败: {ex}")

    @staticmethod
    def _card_surface_only(merged: Dict[str, Any]) -> Dict[str, Any]:
        """
        target=card 时仅落库/预览这些字段；剔除误并入的 Bug/BadCase/TestCase 详情列。
        """
        keys = (
            'title',
            'type',
            'project_id',
            'plan_id',
            'priority',
            'assignee_id',
            'creator_id',
            'description',
        )
        out: Dict[str, Any] = {}
        for k in keys:
            if k not in merged:
                continue
            v = merged[k]
            if v is None and k in ('description', 'assignee_id'):
                continue
            out[k] = v
        return out

    def _validate_card_fields(self, fields: Dict, project_id: int) -> Dict:
        """仅创建 Card 行（迭代卡片总表）；type 为 bug/badcase/testcase/card，默认 bug。"""
        from sqlalchemy.inspection import inspect as sa_inspect
        from app import Card as _Card

        merged = dict(fields or {})
        self._apply_minimal_copy_for_card(merged, project_id)

        merged['project_id'] = int(project_id)
        merged['title'] = str(merged.get('title') or '').strip()
        if not merged['title']:
            raise ValueError('卡片标题不能为空')

        raw_ty = merged.get('type') or merged.get('card_type') or 'bug'
        raw_ty = str(raw_ty).strip().lower()
        if raw_ty in ('bad_case', 'bad-case'):
            raw_ty = 'badcase'
        if raw_ty not in ('bug', 'badcase', 'testcase', 'card'):
            raw_ty = 'bug'
        merged['type'] = raw_ty

        merged['plan_id'] = self._positive_plan_id_or_none(merged.get('plan_id'))

        if merged.get('priority') in (None, ''):
            merged['priority'] = 'p3'
        try:
            merged['creator_id'] = int(merged.get('creator_id') or 0)
        except (TypeError, ValueError):
            merged['creator_id'] = 0

        surface = self._card_surface_only(merged)
        surface['title'] = merged['title']
        surface['project_id'] = int(project_id)
        surface['type'] = raw_ty
        if surface.get('priority') in (None, ''):
            surface['priority'] = 'p3'

        allowed = {c.key for c in sa_inspect(_Card).mapper.column_attrs}
        validated: Dict[str, Any] = {}
        for k, v in surface.items():
            if k not in allowed:
                continue
            if k == 'type':
                validated[k] = raw_ty
                continue
            validated[k] = v

        validated['title'] = merged['title']
        validated['project_id'] = int(project_id)
        validated['type'] = raw_ty
        validated.pop('id', None)
        validated.pop('source_type', None)
        validated.pop('source_id', None)
        return validated
    
    @staticmethod
    def _normalize_bug_title(title: Any) -> str:
        """去掉首尾空白，合并连续空白；若整句指令被写入 title，尽量抽出「标题叫做『xxx』」中的短标题。"""
        if title is None:
            return ''
        s = str(title).strip()
        if not s:
            return ''
        s = re.sub(r'\s+', ' ', s)
        if len(s) > 18:
            extract_patterns = (
                r"标题(?:叫|为|是)\s*['\"]([^'\"]{1,120})['\"]",
                r"标题(?:叫|为|是)\s*[『「]([^』」]{1,120})[』」]",
                r"(?:叫做|称为)\s*['\"]([^'\"]{2,120})['\"]",
            )
            for pat in extract_patterns:
                m = re.search(pat, s)
                if m:
                    inner = (m.group(1) or '').strip()
                    if inner and len(inner) < len(s):
                        s = inner
                        break
            else:
                # 「标题是登录忘记密码有问题」等无引号场景
                m_plain = re.search(r"标题(?:叫|为|是)\s*([^。，；,\n]{2,120})", s)
                if m_plain:
                    inner = (m_plain.group(1) or '').strip()
                    if inner and len(inner) < len(s):
                        s = inner
        return s[:200]

    def _validate_bug_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证 Bug 字段；copy_from_bug_id 时与 testcase 一致：先合并源记录再覆盖非空入参。"""
        from sqlalchemy.inspection import inspect as sa_inspect
        from app import Bug as _Bug

        copy_from = fields.get('copy_from_bug_id') or fields.get('source_bug_id')
        use_copy = copy_from is not None and str(copy_from).strip() != ''
        meta_keys = {'copy_from_bug_id', 'source_bug_id', 'natural_query'}
        merged: Dict[str, Any] = {}
        plan_from_copy = None
        copy_src_bug = None

        if use_copy:
            try:
                src_id = int(copy_from)
                copy_src_bug = self.db.query(_Bug).get(src_id)
                if copy_src_bug:
                    plan_from_copy = self._plan_id_for_bug_copy_merge(copy_src_bug)
                    skip_cols = {'id', 'created_at', 'updated_at', 'card_id'}
                    for col in sa_inspect(_Bug).mapper.column_attrs:
                        key = col.key
                        if key in skip_cols:
                            continue
                        # plan_id 不与源 Bug 列绑定：常与 Card 子迭代不一致，改由 _resolve_plan_id_for_copy + Card 推算
                        if key == 'plan_id':
                            continue
                        merged[key] = getattr(copy_src_bug, key, None)
                    print(
                        f"[CREATE] copy_from_bug_id 合并源 Bug id={copy_src_bug.id} "
                        f"plan_merge={plan_from_copy} bug.plan_id={getattr(copy_src_bug, 'plan_id', None)} "
                        f"project_id={copy_src_bug.project_id} assignee_id={copy_src_bug.assignee_id}"
                    )
                else:
                    print(f"[CREATE] copy_from_bug_id 未找到记录 id={copy_from}")
            except Exception as ex:
                print(f"[CREATE] 加载源 Bug 失败: {ex}")

        for k, v in (fields or {}).items():
            if k in meta_keys:
                continue
            if v is None:
                continue
            if use_copy:
                if v == '' or v == [] or v == {}:
                    continue
                if isinstance(v, str):
                    sv = v.strip()
                    if sv.startswith('[') and sv.endswith(']'):
                        continue
            merged[k] = v

        merged['project_id'] = int(project_id)
        merged['plan_id'] = self._resolve_plan_id_for_copy(
            explicit_raw=merged.get('plan_id'),
            copy_source_id=copy_from if use_copy else None,
            plan_from_copy=plan_from_copy,
        )

        merged['title'] = self._normalize_bug_title(merged.get('title', ''))
        if not merged.get('title'):
            raise ValueError('Bug 标题不能为空')

        # ORM 列为 steps_to_reproduce；兼容 LLM 输出 reproduce_steps
        if merged.get('reproduce_steps') not in (None, '') and not merged.get('steps_to_reproduce'):
            merged['steps_to_reproduce'] = merged['reproduce_steps']

        # 与 ORM / 列表展示一致的缺省，避免预览里只剩标题+项目（复制合并后仍可能缺 status 等）
        if not merged.get('status'):
            merged['status'] = 'new'
        if not merged.get('priority'):
            merged['priority'] = 'p3'
        if not merged.get('severity'):
            merged['severity'] = 'medium'

        allowed = {c.key for c in sa_inspect(_Bug).mapper.column_attrs}
        validated = {k: merged[k] for k in allowed if k in merged}
        validated.pop('id', None)
        # 复制新建：沿用源 Bug 的迭代卡片 id，使多条 Bug 归属同一「卡片目录」下（无 card_id 时再走落库创建 Card）
        reuse_cid = None
        if use_copy and copy_src_bug is not None:
            raw_c = getattr(copy_src_bug, 'card_id', None)
            if raw_c is not None and str(raw_c).strip() != '':
                try:
                    reuse_cid = int(raw_c)
                except (TypeError, ValueError):
                    reuse_cid = None
            if reuse_cid is None:
                try:
                    from app import Card as _Card
                    from app import CardType

                    c = (
                        self.db.query(_Card)
                        .filter(_Card.source_id == int(copy_src_bug.id))
                        .filter(_Card.type == CardType.BUG)
                        .first()
                    )
                    if c:
                        reuse_cid = int(c.id)
                except Exception:
                    pass
        if reuse_cid:
            validated['card_id'] = reuse_cid
            try:
                from app import Card as _Card

                crow = self.db.query(_Card).get(reuse_cid)
                if crow is not None:
                    cp = getattr(crow, 'plan_id', None)
                    if cp is not None and str(cp).strip() != '':
                        try:
                            pi = int(cp)
                            if pi > 0:
                                validated['plan_id'] = pi
                        except (TypeError, ValueError):
                            pass
            except Exception:
                pass
        else:
            validated.pop('card_id', None)
        return validated
    
    def _validate_badcase_fields(self, fields: Dict, project_id: int) -> Dict:
        """验证 BadCase 字段；带 copy_from_badcase_id 时与 Bug 一致：先全量合并源行再覆盖非空入参。"""
        from sqlalchemy.inspection import inspect as sa_inspect
        from app import BadCase as _BC

        copy_from = fields.get('copy_from_badcase_id') or fields.get('source_badcase_id')
        use_copy = copy_from is not None and str(copy_from).strip() != ''
        meta_keys = {'copy_from_badcase_id', 'source_badcase_id', 'natural_query'}
        merged: Dict[str, Any] = {}
        plan_from_copy = None

        if use_copy:
            try:
                src_id = int(copy_from)
                src = self.db.query(_BC).get(src_id)
                if src:
                    plan_from_copy = src.plan_id
                    skip_cols = {'id', 'created_at', 'updated_at'}
                    for col in sa_inspect(_BC).mapper.column_attrs:
                        key = col.key
                        if key in skip_cols:
                            continue
                        merged[key] = getattr(src, key, None)
                    print(
                        f"[CREATE] copy_from_badcase_id 合并源 id={src.id} plan_id={src.plan_id} "
                        f"project_id={src.project_id}"
                    )
                else:
                    print(f"[CREATE] copy_from_badcase_id 未找到记录 id={copy_from}")
            except Exception as ex:
                print(f"[CREATE] 加载源 BadCase 失败: {ex}")

        for k, v in (fields or {}).items():
            if k in meta_keys:
                continue
            if v is None:
                continue
            if use_copy:
                if v == '' or v == [] or v == {}:
                    continue
                if isinstance(v, str):
                    sv = v.strip()
                    if sv.startswith('[') and sv.endswith(']'):
                        continue
            merged[k] = v

        merged['project_id'] = int(project_id)
        merged['plan_id'] = self._resolve_plan_id_for_copy(
            explicit_raw=merged.get('plan_id'),
            copy_source_id=copy_from if use_copy else None,
            plan_from_copy=plan_from_copy,
        )

        merged['title'] = str(merged.get('title') or '').strip()
        if not merged.get('title'):
            raise ValueError('BadCase 标题不能为空')

        if not use_copy:
            merged.setdefault('case_category', '未分类')
            merged.setdefault('base_problem', '')
            merged.setdefault('badcase_result', '')
            merged.setdefault('answer', '')

        allowed = {c.key for c in sa_inspect(_BC).mapper.column_attrs}
        validated = {k: merged[k] for k in allowed if k in merged}
        validated.pop('id', None)
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
                    'copy_from_badcase_id', 'source_badcase_id',
                    'copy_from_card_id', 'source_card_id',
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
                    # 已带 card_id（如复制到同一迭代卡片下）：不再新建 Card，与 /api/bugs 行为一致
                    if getattr(bug, "card_id", None):
                        return bug.id
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
                        self.db.refresh(card)
                        try:
                            badcase.card_id = int(card.id)
                            self.db.add(badcase)
                            self.db.commit()
                            self.db.refresh(badcase)
                        except Exception:
                            self.db.rollback()
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
                        self.db.refresh(card)
                        try:
                            testcase.card_id = int(card.id)
                            self.db.add(testcase)
                            self.db.commit()
                            self.db.refresh(testcase)
                        except Exception:
                            self.db.rollback()
                    except Exception:
                        self.db.rollback()
                    return testcase.id

                elif target == 'card':
                    from sqlalchemy.inspection import inspect as sa_inspect
                    from app import Card, CardType

                    fd = dict(fields or {})
                    ty_raw = str(fd.pop('type', 'bug') or 'bug').strip().lower()
                    if ty_raw in ('bad_case', 'bad-case'):
                        ty_raw = 'badcase'
                    type_map = {
                        'bug': CardType.BUG,
                        'badcase': CardType.BADCASE,
                        'testcase': CardType.TESTCASE,
                        'card': CardType.CARD,
                    }
                    ct_enum = type_map.get(ty_raw, CardType.BUG)

                    card_cols = {c.key for c in sa_inspect(Card).mapper.column_attrs}
                    kwargs: Dict[str, Any] = {}
                    for k, v in fd.items():
                        if k not in card_cols or k == 'type':
                            continue
                        kwargs[k] = v
                    kwargs['type'] = ct_enum
                    kwargs.setdefault('title', fd.get('title') or '')
                    kwargs.setdefault('project_id', int(project_id))
                    kwargs.setdefault('creator_id', int(fd.get('creator_id') or 0))
                    kwargs.setdefault('priority', fd.get('priority') or 'p3')
                    if fd.get('plan_id') is not None:
                        kwargs['plan_id'] = self._positive_plan_id_or_none(fd.get('plan_id'))

                    card = Card(**kwargs)
                    self.db.add(card)
                    self.db.commit()
                    self.db.refresh(card)
                    return int(card.id)

                return None
            
        except Exception as e:
            print(f"[CREATE] 创建记录失败: {e}")
            self.db.rollback()
            return None

    @staticmethod
    def _bug_preview_display_value(field: str, value: Any) -> str:
        """Bug 新建预览：空 plan/负责人等也要展示占位，否则 diff 只剩标题和 project_id。"""
        if field == 'plan_id':
            if value is None or value == '':
                return '（未关联计划）'
            try:
                n = int(value)
                return str(n) if n > 0 else '（未关联计划）'
            except (TypeError, ValueError):
                return str(value)
        if field == 'assignee_id':
            if value is None or value == '':
                return '（未指派）'
            return str(value)
        if value is None:
            return '（空）'
        if isinstance(value, str) and not value.strip():
            return '（空）'
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    def _generate_bug_create_diff(self, fields: Dict, field_labels: Dict[str, str], skip_fields: set) -> List[Dict]:
        """Bug：按产品关心的顺序输出预览行；复制场景下列表字段齐全可见。"""
        order = [
            'title',
            'project_id',
            'plan_id',
            'status',
            'priority',
            'severity',
            'assignee_id',
            'bug_type',
            'environment',
            'browser',
            'os',
            'description',
            'steps_to_reproduce',
            'expected_result',
            'actual_result',
            'attachments',
        ]
        seen: set = set()
        diff_result: List[Dict] = []
        for field in order:
            if field in skip_fields:
                continue
            if field not in fields:
                continue
            seen.add(field)
            value_str = self._bug_preview_display_value(field, fields[field])
            lines = value_str.split('\n') if '\n' in value_str else [value_str]
            parsed_lines = [{'type': 'add', 'content': line, 'line_no': i} for i, line in enumerate(lines)]
            diff_result.append({
                'field': field,
                'field_label': field_labels.get(field, field),
                'lines': parsed_lines,
            })
        for field, value in fields.items():
            if field in seen or field in skip_fields:
                continue
            value_str = self._bug_preview_display_value(field, value)
            lines = value_str.split('\n') if '\n' in value_str else [value_str]
            parsed_lines = [{'type': 'add', 'content': line, 'line_no': i} for i, line in enumerate(lines)]
            diff_result.append({
                'field': field,
                'field_label': field_labels.get(field, field),
                'lines': parsed_lines,
            })
        return diff_result

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
            'project_id': '所属项目',
            'attachments': '附件',
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
            # Card 总表（target=card）
            'type': '卡片类型',
        }
        
        # 需要跳过的系统字段
        skip_fields = {
            'id', 'creator_id', 'created_at', 'updated_at',
            'copy_from_testcase_id', 'source_testcase_id',
            'copy_from_bug_id', 'source_bug_id',
            'copy_from_badcase_id', 'source_badcase_id',
            'copy_from_card_id', 'source_card_id',
        }

        if (target or '').strip().lower() == 'bug':
            return self._generate_bug_create_diff(fields, field_labels, skip_fields)

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
