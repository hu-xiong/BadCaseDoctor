"""
Grep Tool - 缺陷定位工具
模拟人类测试工程师的思维模式，精准定位 BadCase/Bug/测试用例的归属关系
"""
from typing import Dict, Any, List, Callable, Optional, Tuple
from collections import defaultdict
import json
import os
import time

from sqlalchemy import or_
from agents.tool_registry import BaseTool
from agents.locale_prompts import (
    normalize_locale,
    is_english_locale,
    grep_tool_progress,
    grep_plan_material_progress,
    grep_generate_locate_summary,
    enrich_grep_observation_nl_with_plan_names,
    grep_associate_summary,
    grep_compare_summary,
)


class GrepTool(BaseTool):
    """
    缺陷定位工具
    
    核心能力：
    1. 分析计划树结构，理解业务分类
    2. 解析列表内容，识别关键信息
    3. 结合执行证据，关联业务场景
    4. 输出定位结论，明确归属关系
    """
    
    def __init__(self):
        # project_id -> (plan_tree_dict, unix_ts)；GREP_PLAN_TREE_CACHE_TTL 秒，0 关闭
        self._plan_tree_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        super().__init__(
            name="grep",
            description="缺陷定位工具：模拟人类阅读习惯，先检索再阅读。精准定位 BadCase/Bug/测试用例/统一卡片(Card)的归属关系和业务场景。"
                         "必须参数：project_id(项目ID)。可选：keywords(标题关键词，拆分后默认「任一词命中」OR；需全部命中可设环境变量 GREP_KEYWORDS_MATCH_MODE=and), "
                         "target(bug/badcase/testcase/card/plan/all；card=仅查 Card；plan=仅查迭代计划 Plan；all=多类)，status，plan_id(当前迭代)，card_id(可选)。"
                         "代码结构分析可选：code_paths（逗号/分号分隔的 .py 文件路径）、prefer_ast_structure=true 或 mode=code_ast 时优先 Python AST 解析，结果写入 data.code_ast。"
                         "返回 plan_tree、badcase_analysis、bug_location、testcase_location、card_location（Card 表）。建议先用 plan_id 限定迭代计划，再把候选记录交给大模型逐条阅读判断。"
        )
    
    async def execute(
        self,
        keywords: str = None,
        project_id: str = None,
        plan_id: str = None,  # 当前迭代计划ID，传入则只检索该计划下的记录
        card_id: str = None,  # 当前卡片ID（可选；用于将 navigation.record_id 对齐到卡片列表）
        plan_context: str = None,
        evidence: Dict[str, Any] = None,
        mode: str = "locate",  # locate/associate/compare
        target: str = "all",  # all/bug/badcase/testcase/card
        status: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行缺陷定位分析
        
        Args:
            keywords: 搜索关键词（如"登录"、"商品"）
            project_id: 项目ID
            plan_context: 计划上下文（当前查看的计划树结构）
            evidence: 执行证据（工具调用记录）
            mode: 执行模式
                - locate: 定位归属计划（默认）
                - associate: 三向关联分析（BadCase↔Bug↔TestCase）
                - compare: 修改前后对比
            target: 分析目标
                - all: BadCase / Bug / TestCase / Card（默认）
                - bug / badcase / testcase / card: 仅分析对应一类；card 查 Card 表标题与描述
            status: 按状态过滤（如 "closed", "new", "pending" 等）
            **kwargs: 其他参数
            
        Returns:
            定位分析结果（包含思考过程）
        """
        if keywords is not None and not isinstance(keywords, str):
            if isinstance(keywords, (list, tuple)):
                keywords = " ".join(
                    str(x).strip() for x in keywords if x is not None and str(x).strip()
                )
            else:
                keywords = str(keywords).strip() or None
        raw_target = (target or "all").strip().lower() if isinstance(target, str) else "all"
        if raw_target not in ("all", "bug", "badcase", "testcase", "card", "plan"):
            raw_target = "all"
        print(
            f"[GREP] 🔍 开始定位 (keywords={keywords}, target={raw_target}, status={status}, plan_id={plan_id})"
        )
        
        progress_callback = kwargs.get("progress_callback")
        loc = normalize_locale(kwargs.get("ui_locale"))

        def _progress(msg: str):
            try:
                s = str(msg)
                if callable(progress_callback):
                    progress_callback(s)
            except Exception:
                pass
        
        _progress(grep_tool_progress("init", loc))

        try:
            from app import app, db, BadCase, Bug, Plan
            
            result = {
                'success': True,
                'mode': mode,
                'thinking_process': [],
                'data': {}
            }

            # 代码结构分析：优先 AST（Python），无有效结果再依赖后续 DB/文本检索
            _code_paths = kwargs.get("code_paths")
            _want_ast = bool(kwargs.get("prefer_ast_structure")) or mode == "code_ast"
            if _want_ast and _code_paths:
                try:
                    from agents.tools.code_ast_parser import analyze_code_paths

                    _ast = analyze_code_paths(_code_paths)
                    result["data"]["code_ast"] = _ast
                    if _ast.get("success"):
                        _progress("code_ast: ok")
                        result["thinking_process"].append(
                            {"phase": "code_ast", "merged_symbols": _ast.get("merged_symbols")}
                        )
                except Exception as _ast_e:
                    result["data"]["code_ast"] = {"success": False, "error": str(_ast_e)}
            
            with app.app_context():
                if mode == "locate":
                    # 【阶段1】数据库查询（支持 plan_id 限定当前迭代，关键词拆分模糊匹配）
                    _progress(grep_tool_progress("phase1_plan_tree", loc))
                    plan_tree = await self._get_plan_tree(project_id)
                    _progress(grep_tool_progress("phase1_plan_ready", loc))

                    if raw_target == "plan":
                        plan_records_tree = None
                        if plan_id:
                            _progress(grep_tool_progress("plan_material_read", loc))
                            plan_records_tree = await self._build_plan_records_tree(
                                project_id=project_id,
                                root_plan_id=plan_id,
                                progress_callback=progress_callback,
                                ui_locale=loc,
                            )
                            _progress(grep_tool_progress("plan_material_ready", loc))
                        plan_location = self._get_plan_entity_list(project_id, keywords, plan_id)
                        en = is_english_locale(loc)
                        if not plan_location:
                            summary_plan = (
                                "📅 No matching iteration plans."
                                if en
                                else "📅 未找到匹配的迭代计划。"
                            )
                        else:
                            summary_plan = (
                                f"📅 Found {len(plan_location)} iteration plan(s)."
                                if en
                                else f"📅 找到 {len(plan_location)} 个迭代计划（target=plan）。"
                            )
                        plan_attr = [
                            {"id": x["id"], "name": x.get("name"), "plan_id": x["id"]}
                            for x in plan_location
                        ]
                        navigation_list = self._build_grep_navigation_items(
                            plan_tree,
                            "plan",
                            [],
                            [],
                            [],
                            [],
                            scope_plan_id=plan_id,
                            plan_entity_list=plan_location,
                        )
                        navigation = (
                            {"type": "multiple", "items": navigation_list}
                            if navigation_list
                            else None
                        )
                        if navigation_list:
                            _progress(grep_tool_progress("nav_build", loc))
                            print(
                                f"[GREP] ✅ 计划实体检索: n={len(plan_location)} nav={len(navigation_list)}"
                            )
                        result["data"] = {
                            "plan_tree": plan_tree,
                            "plan_records_tree": plan_records_tree,
                            "plan_location": plan_location,
                            "badcase_analysis": [],
                            "bug_location": [],
                            "testcase_location": [],
                            "card_location": [],
                            "plan_attribution": plan_attr,
                            "comparison_report": "",
                            "summary": summary_plan,
                            "navigation": navigation,
                        }
                    else:
                        # 人类阅读模式：如果指定了 plan_id，则返回该计划及其子计划的树形结构，并挂载各计划下的记录（从上到下、从外到里）
                        plan_records_tree = None
                        if plan_id:
                            _progress(grep_tool_progress("plan_material_read", loc))
                            plan_records_tree = await self._build_plan_records_tree(
                                project_id=project_id,
                                root_plan_id=plan_id,
                                progress_callback=progress_callback,
                                ui_locale=loc,
                            )
                            _progress(grep_tool_progress("plan_material_ready", loc))
                    
                        badcase_list = []
                        bug_list = []
                        testcase_list = []
                        card_list: List[Dict[str, Any]] = []
                        if raw_target in ['all', 'badcase']:
                            _progress(grep_tool_progress("phase1_badcase", loc))
                            badcase_list = await self._get_badcase_list(project_id, keywords, status, plan_id=plan_id)
                            _progress(grep_tool_progress("phase1_badcase_done", loc, n=len(badcase_list)))
                        if raw_target in ['all', 'bug']:
                            _progress(grep_tool_progress("phase1_bug", loc))
                            bug_list = await self._get_bug_list(project_id, keywords, status, plan_id=plan_id)
                            _progress(grep_tool_progress("phase1_bug_done", loc, n=len(bug_list)))
                        if raw_target in ['all', 'testcase']:
                            _progress(grep_tool_progress("phase1_tc", loc))
                            testcase_list = await self._get_testcase_list(project_id, keywords, status, plan_id=plan_id)
                            _progress(grep_tool_progress("phase1_tc_done", loc, n=len(testcase_list)))
                        # 卡片层：target=all|card 照常拉取；单独查 bug/badcase/testcase 时也拉取，
                        # 否则 navigation 无法合并为「统一卡片」跳转，迭代下列表里卡片命中也不会出现。
                        if raw_target in ('all', 'card', 'bug', 'badcase', 'testcase'):
                            _progress(grep_tool_progress("phase1_card", loc))
                            card_list = await self._get_card_list(project_id, keywords, plan_id=plan_id)
                            _progress(grep_tool_progress("phase1_card_done", loc, n=len(card_list)))

                        # 卡片层适配：为导航补充 card_id（优先按 Card.source_type/source_id 映射）
                        try:
                            from app import db as _db, Card as _Card

                            def _attach_card_ids(items: List[Dict[str, Any]], st: str) -> None:
                                if not items:
                                    return
                                ids = []
                                for it in items:
                                    try:
                                        iid = int(it.get("id"))
                                        ids.append(iid)
                                    except Exception:
                                        pass
                                if not ids:
                                    return
                                sid_set = list(set(ids))
                                rows = (
                                    _db.session.query(_Card)
                                    .filter(_Card.project_id == int(project_id))
                                    .filter(_Card.source_id.in_(sid_set))
                                    .all()
                                )
                                by_sid: Dict[int, List[Any]] = defaultdict(list)
                                for r in rows:
                                    si = getattr(r, "source_id", None)
                                    if si is None:
                                        continue
                                    try:
                                        by_sid[int(si)].append(r)
                                    except Exception:
                                        continue
                                for it in items:
                                    if it.get("card_id") is not None:
                                        continue
                                    try:
                                        sid = int(it.get("id"))
                                    except Exception:
                                        continue
                                    picked = self._pick_card_orm_from_candidates(by_sid.get(sid) or [], st)
                                    if picked is not None:
                                        try:
                                            it["card_id"] = int(getattr(picked, "id"))
                                        except (TypeError, ValueError):
                                            pass
                                        ct = (getattr(picked, "title", None) or "").strip()
                                        if ct:
                                            it["card_title"] = ct
                                            if not (it.get("title") or "").strip():
                                                it["title"] = ct

                            _attach_card_ids(bug_list, "bug")
                            _attach_card_ids(badcase_list, "badcase")
                            _attach_card_ids(testcase_list, "testcase")
                        except Exception:
                            pass
                    
                        # 【阶段2】分析关联
                        _progress(grep_tool_progress("phase2_assoc", loc))
                        analysis_result = await self._analyze_associations(
                            keywords=keywords,
                            plan_tree=plan_tree,
                            badcase_list=badcase_list,
                            bug_list=bug_list,
                            testcase_list=testcase_list,
                            card_list=card_list,
                            evidence=evidence,
                            ui_locale=loc,
                            plan_records_tree=plan_records_tree,
                        )
                        _progress(grep_tool_progress("phase2_done", loc))
                    
                        # 【阶段3】生成对比报告
                        _progress(grep_tool_progress("phase3_compare", loc))
                        comparison = await self._generate_comparison(project_id, keywords)
                        _progress(grep_tool_progress("phase3_done", loc))
                    
                        # 生成导航指令（Bug / BadCase / TestCase，随 grep target 过滤；all 时合并多类）
                        navigation = None
                        navigation_list = self._build_grep_navigation_items(
                            plan_tree,
                            raw_target,
                            badcase_list,
                            bug_list,
                            testcase_list,
                            card_list,
                            scope_plan_id=plan_id,
                        )
                        if navigation_list:
                            _progress(grep_tool_progress("nav_build", loc))
                            # 始终使用 type=multiple + items，与前端 SimpleChatPanel / AgentTaskRun 一致；
                            # 单条时若只返回 expand_and_locate，界面不渲染「点击跳转」列表。
                            navigation = {'type': 'multiple', 'items': navigation_list}
                            print(
                                f"[GREP] ✅ 定位完成: Bug={len(bug_list)} BadCase={len(badcase_list)} "
                                f"TestCase={len(testcase_list)} Card={len(card_list)}，导航条目={len(navigation_list)}"
                            )
                            print(
                                f"[MODIFY-TRACE] grep_tool: grep_target={raw_target!r}, nav_len={len(navigation_list)} "
                                f"(未计划 plan_id 为空也会进导航)"
                            )
                            _progress(grep_tool_progress("locate_done_nav", loc))
                    
                        result['data'] = {
                            'plan_tree': plan_tree,
                            'plan_records_tree': plan_records_tree,
                            'plan_location': [],
                            'badcase_analysis': analysis_result['badcase_analysis'],
                            'bug_location': analysis_result['bug_location'],
                            'testcase_location': analysis_result.get('testcase_location', []),
                            'card_location': analysis_result.get('card_location', []),
                            'plan_attribution': analysis_result['plan_attribution'],
                            'comparison_report': comparison['markdown'],
                            'summary': analysis_result['summary'],
                            'navigation': navigation
                        }
                    

                elif mode == "associate":
                    # 三向关联模式
                    _progress(grep_tool_progress("assoc_start", loc))
                    associations = await self._three_way_association(project_id, keywords)
                    _progress(grep_tool_progress("assoc_done", loc))
                    result['data'] = {
                        'associations': associations,
                        'total_associations': len(associations),
                        'summary': grep_associate_summary(len(associations), loc),
                    }
                    
                elif mode == "compare":
                    # 对比模式
                    _progress(grep_tool_progress("compare_start", loc))
                    comparison = await self._generate_comparison(project_id, keywords)
                    _progress(grep_tool_progress("compare_done", loc))
                    result['data'] = {
                        'comparison': comparison,
                        'markdown': comparison['markdown'],
                        'changes_count': len(comparison['changes']),
                        'summary': grep_compare_summary(len(comparison['changes']), loc),
                    }
                
                return result
                
        except Exception as e:
            print(f"[GREP] ❌ 定位分析失败: {e}")
            _progress(grep_tool_progress("locate_fail", loc, err=e))
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }



    def _get_plan_entity_list(
        self,
        project_id: Any,
        keywords: Optional[str],
        scope_plan_id: Any = None,
    ) -> List[Dict[str, Any]]:
        """检索迭代计划 Plan 表；scope_plan_id 有值时仅 root 及其子孙计划。"""
        from app import db, Plan

        try:
            pid = int(project_id)
        except (TypeError, ValueError):
            return []
        rows = db.session.query(Plan).filter(Plan.project_id == pid).all()
        candidates = list(rows)
        if scope_plan_id not in (None, "", "0"):
            try:
                root = int(scope_plan_id)
            except (TypeError, ValueError):
                root = None
            else:
                children_map: Dict[Any, List[int]] = {}
                for p in rows:
                    children_map.setdefault(p.parent_id, []).append(p.id)
                allowed = {root}
                stack = [root]
                while stack:
                    cur = stack.pop()
                    for cid in children_map.get(cur, []):
                        if cid not in allowed:
                            allowed.add(cid)
                            stack.append(cid)
                candidates = [p for p in rows if p.id in allowed]

        kw_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_all = not kw_list and (
            not keywords or str(keywords).strip() in ("", "*")
        )
        if not is_all and kw_list:
            filtered = []
            for p in candidates:
                hay = f"{p.name or ''} {(p.description or '')}"
                if self._text_matches_normalized_keywords(hay, keywords):
                    filtered.append(p)
            candidates = filtered
        elif not is_all and keywords and str(keywords).strip():
            k = str(keywords).strip().lower()
            candidates = [
                p
                for p in candidates
                if (p.name and k in (p.name or "").lower())
                or (p.description and k in (p.description or "").lower())
            ]

        candidates.sort(
            key=lambda x: (x.updated_at or x.created_at or x.id),
            reverse=True,
        )
        out: List[Dict[str, Any]] = []
        for p in candidates[:80]:
            out.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "title": p.name,
                    "description": (p.description or "")[:800],
                    "status": p.status,
                    "priority": p.priority,
                    "project_id": p.project_id,
                    "parent_id": p.parent_id,
                    "plan_id": p.id,
                    "is_default": getattr(p, "is_default", False),
                }
            )
        return out
    async def _build_plan_records_tree(
        self,
        project_id: str,
        root_plan_id: str,
        progress_callback: Optional[Callable[[str], None]] = None,
        ui_locale: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        构建“计划树 + 计划下记录”的阅读结构：
        - 从 root_plan_id 出发，递归包含所有子计划
        - 每个计划节点挂载 badcases/bugs/testcases（包含尽可能完整字段，便于大模型逐条阅读判断）
        """
        def _p(msg: str):
            try:
                if callable(progress_callback):
                    progress_callback(str(msg))
            except Exception:
                pass

        from app import db, Plan, BadCase, Bug, TestCase
        ploc = normalize_locale(ui_locale)
        try:
            root_id = int(root_plan_id)
        except (ValueError, TypeError):
            return None

        # 取该项目下所有计划，构建 parent->children
        _p(grep_plan_material_progress("load_plans", ploc))
        plans = db.session.query(Plan).filter_by(project_id=project_id).all()
        plan_map = {}
        children_map = {}
        for p in plans:
            plan_map[p.id] = p
            children_map.setdefault(p.parent_id, []).append(p.id)

        # 收集 root 下所有 plan_ids（含子孙）
        plan_ids = []
        stack = [root_id]
        visited = set()
        while stack:
            pid = stack.pop()
            if pid in visited:
                continue
            visited.add(pid)
            if pid in plan_map:
                plan_ids.append(pid)
                for cid in children_map.get(pid, []):
                    stack.append(cid)

        # 查询三类记录（不做 rerank/不做筛选，仅按 plan_id 归类，模拟人类先把材料拿全）
        _p(grep_plan_material_progress("query_under_plans", ploc, n=len(plan_ids)))
        badcases = db.session.query(BadCase).filter(BadCase.project_id == int(project_id), BadCase.plan_id.in_(plan_ids)).all() if plan_ids else []
        bugs = db.session.query(Bug).filter(Bug.project_id == int(project_id), Bug.plan_id.in_(plan_ids)).all() if plan_ids else []
        testcases = db.session.query(TestCase).filter(TestCase.project_id == int(project_id), TestCase.plan_id.in_(plan_ids)).all() if plan_ids else []
        _p(
            grep_plan_material_progress(
                "assemble", ploc, bc=len(badcases), b=len(bugs), tc=len(testcases)
            )
        )

        badcase_by_plan = {}
        for bc in badcases:
            badcase_by_plan.setdefault(bc.plan_id, []).append(bc.to_dict() if hasattr(bc, 'to_dict') else {
                'id': bc.id, 'title': bc.title, 'plan_id': bc.plan_id
            })
        bug_by_plan = {}
        for b in bugs:
            bug_by_plan.setdefault(b.plan_id, []).append(b.to_dict() if hasattr(b, 'to_dict') else {
                'id': b.id, 'title': b.title, 'plan_id': b.plan_id
            })
        testcase_by_plan = {}
        for tc in testcases:
            testcase_by_plan.setdefault(tc.plan_id, []).append(tc.to_dict() if hasattr(tc, 'to_dict') else {
                'id': tc.id, 'title': tc.title, 'plan_id': tc.plan_id
            })

        def plan_to_dict(p: Plan) -> Dict[str, Any]:
            return {
                'id': p.id,
                'name': p.name,
                'description': getattr(p, 'description', ''),
                'status': getattr(p, 'status', None),
                'priority': getattr(p, 'priority', None),
                'is_pinned': getattr(p, 'is_pinned', None),
                'start_date': p.start_date.isoformat() if getattr(p, 'start_date', None) else None,
                'end_date': p.end_date.isoformat() if getattr(p, 'end_date', None) else None,
                'progress': getattr(p, 'progress', None),
                'parent_id': getattr(p, 'parent_id', None),
                'project_id': getattr(p, 'project_id', None),
                'creator_id': getattr(p, 'creator_id', None),
                'assignee_id': getattr(p, 'assignee_id', None),
                'cycle': getattr(p, 'cycle', None),
                'plan_count': getattr(p, 'plan_count', None),
                'scope_notification': getattr(p, 'scope_notification', None),
                'created_at': p.created_at.isoformat() if getattr(p, 'created_at', None) else None,
                'updated_at': p.updated_at.isoformat() if getattr(p, 'updated_at', None) else None,
            }

        def build_node(pid: int) -> Dict[str, Any]:
            p = plan_map.get(pid)
            if not p:
                return {}
            node = {
                'plan': plan_to_dict(p),
                'badcases': badcase_by_plan.get(pid, []),
                'bugs': bug_by_plan.get(pid, []),
                'testcases': testcase_by_plan.get(pid, []),
                'children': []
            }
            for cid in sorted(children_map.get(pid, [])):
                child_node = build_node(cid)
                if child_node:
                    node['children'].append(child_node)
            return node

        _p("计划材料：递归组装计划树节点…")
        tree = build_node(root_id)
        _p("计划材料：树结构组装完成")
        return tree
    
    async def _get_plan_tree(self, project_id: str) -> Dict[str, Any]:
        """
        计划阅读器：解析迭代计划结构（优化版）
        """
        try:
            ttl = float(os.getenv("GREP_PLAN_TREE_CACHE_TTL", "60") or "60")
        except Exception:
            ttl = 60.0
        key = str(project_id)
        if ttl > 0 and key in self._plan_tree_cache:
            cached, ts = self._plan_tree_cache[key]
            if time.time() - ts < ttl:
                return cached

        from app import db, Plan
        
        # 查询项目下所有计划（单次查询）
        plans = db.session.query(Plan).filter_by(project_id=project_id).all()
        
        # 构建树形结构
        plan_map = {}
        root_plans = []
        
        for plan in plans:
            plan_data = {
                'id': plan.id,
                'name': plan.name,
                'status': plan.status,
                'parent_id': plan.parent_id,
                'description': getattr(plan, 'description', ''),
                'children': [],
                'keywords': self._extract_keywords(plan.name),
                'business_domain': self._infer_business_domain(plan.name)
            }
            plan_map[plan.id] = plan_data
            
            if not plan.parent_id:
                root_plans.append(plan_data)
        
        # 构建父子关系
        for plan_data in plan_map.values():
            if plan_data['parent_id'] and plan_data['parent_id'] in plan_map:
                plan_map[plan_data['parent_id']]['children'].append(plan_data)
        
        result = {
            'total_plans': len(plans),
            'root_plans': root_plans,
            'plans': list(plan_map.values()),  # 扁平列表便于查找
            'plan_map': plan_map,
            'business_domains': list(set(p['business_domain'] for p in plan_map.values()))
        }
        if ttl > 0:
            self._plan_tree_cache[key] = (result, time.time())
        return result

    def _plan_display_name(self, plan_tree: Optional[Dict[str, Any]], plan_id: Any) -> str:
        """从 plan_tree 扁平 plans 列表解析计划名称（用于导航卡片）。"""
        if plan_id is None or not plan_tree:
            return ''
        for p in plan_tree.get('plans') or []:
            if p.get('id') == plan_id:
                return (p.get('name') or '').strip()
        return ''

    @staticmethod
    def _grep_nav_target_priority(target: str) -> int:
        """同一 record_id 合并时优先保留「统一卡片」跳转，避免 target=all 下列四条重复。"""
        t = (target or "").strip().lower()
        return {"card": 0, "bug": 1, "badcase": 2, "testcase": 3, "plan": 4}.get(t, 9)

    @staticmethod
    def _pick_card_orm_from_candidates(candidates: List[Any], target_kind: str) -> Optional[Any]:
        """与 modify_tool._find_card_for_source_row 一致：不按 source_type SQL 硬过滤，避免库内枚举写法不一致导致丢关联。"""
        if not candidates:
            return None
        try:
            from app import CardType
        except Exception:
            CardType = None  # type: ignore

        tk = (target_kind or "").strip().lower()
        aliases = {
            "bug": ["bug"],
            "badcase": ["badcase", "bad_case"],
            "testcase": ["testcase", "test_case"],
        }
        norm_set = {a.replace("-", "_").lower() for a in aliases.get(tk, [])}
        expected_ct = None
        if CardType is not None:
            expected_ct = {
                "bug": CardType.BUG,
                "badcase": CardType.BADCASE,
                "testcase": CardType.TESTCASE,
            }.get(tk)

        for c in candidates:
            st = str(getattr(c, "source_type", None) or "").strip().lower().replace("-", "_")
            if st in norm_set:
                return c
        if expected_ct is not None:
            for c in candidates:
                if getattr(c, "type", None) == expected_ct:
                    return c
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _collapse_navigation_merge_keys(
        self,
        best_by_rid: Dict[int, Tuple[int, Dict[str, Any]]],
        card_list: List[Dict[str, Any]],
        plan_tree: Optional[Dict[str, Any]],
    ) -> Dict[int, Tuple[int, Dict[str, Any]]]:
        """
        源表 Bug/BadCase/TestCase 与 Card 指向同一业务对象时，grep 会同时命中两行；
        按 Card.source_type/source_id 合并为一条 target=card（与迭代卡片列表一致）。
        """
        card_list = card_list or []
        bug_sid_to_cid: Dict[int, int] = {}
        bc_sid_to_cid: Dict[int, int] = {}
        tc_sid_to_cid: Dict[int, int] = {}
        cid_meta: Dict[int, Dict[str, Any]] = {}

        def _npid(raw: Any) -> Any:
            if raw is None or raw == "":
                return None
            try:
                n = int(raw)
                return n if n > 0 else None
            except (TypeError, ValueError):
                return None

        for c in card_list:
            raw_cid = c.get("card_id") if c.get("card_id") is not None else c.get("id")
            if raw_cid is None:
                continue
            try:
                cid = int(raw_cid)
            except (TypeError, ValueError):
                continue
            cid_meta[cid] = c
            sid = c.get("source_id")
            if sid is None:
                continue
            try:
                sid_i = int(sid)
            except (TypeError, ValueError):
                continue
            st = str(c.get("source_type") or "").lower()
            if st == "bug":
                bug_sid_to_cid[sid_i] = cid
            elif st in ("bad_case", "badcase"):
                bc_sid_to_cid[sid_i] = cid
            elif st in ("test_case", "testcase"):
                tc_sid_to_cid[sid_i] = cid

        merged: Dict[int, Tuple[int, Dict[str, Any]]] = {}

        def merge_entry(canon_rid: int, pri: int, ent: Dict[str, Any]) -> None:
            if canon_rid not in merged:
                merged[canon_rid] = (pri, ent)
                return
            old_pri, old_ent = merged[canon_rid]
            if pri < old_pri:
                merged[canon_rid] = (pri, ent)
            elif pri == old_pri:
                nt = str(ent.get("target") or "").lower()
                ot = str(old_ent.get("target") or "").lower()
                if nt == "card" and ot != "card":
                    merged[canon_rid] = (pri, ent)
                elif nt == ot == "card":
                    # 同一张卡片：纯关键词命中的 Card 行 vs 源表升级行；优先保留带 legacy_row_id（对应具体 Bug/用例）
                    el = ent.get("legacy_row_id")
                    ol = old_ent.get("legacy_row_id")
                    if el and not ol:
                        merged[canon_rid] = (pri, ent)

        for rid, (pri, ent) in best_by_rid.items():
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                continue
            t = str(ent.get("target") or "").lower()
            canon = rid_int
            upgraded = False
            if t == "bug":
                bid = ent.get("bug_id")
                try:
                    bi = int(bid) if bid is not None else None
                except (TypeError, ValueError):
                    bi = None
                if bi is not None and bi in bug_sid_to_cid:
                    canon = bug_sid_to_cid[bi]
                    upgraded = True
            elif t == "badcase":
                si = ent.get("source_id")
                try:
                    si_i = int(si) if si is not None else None
                except (TypeError, ValueError):
                    si_i = None
                if si_i is not None and si_i in bc_sid_to_cid:
                    canon = bc_sid_to_cid[si_i]
                    upgraded = True
            elif t == "testcase":
                si = ent.get("source_id")
                try:
                    si_i = int(si) if si is not None else None
                except (TypeError, ValueError):
                    si_i = None
                if si_i is not None and si_i in tc_sid_to_cid:
                    canon = tc_sid_to_cid[si_i]
                    upgraded = True

            if upgraded:
                cm = cid_meta.get(canon) or {}
                # 导航文案必须与 grep 命中的源表行一致；Card.title 可能滞后或与另一条 Bug 共用卡片展示名，勿优先用 cm
                title = (ent.get("title") or cm.get("title") or "").strip()
                pid = _npid(cm.get("plan_id"))
                if pid is None:
                    pid = _npid(ent.get("plan_id"))
                legacy_row_id = None
                try:
                    if t == "bug" and ent.get("bug_id") is not None:
                        legacy_row_id = int(ent.get("bug_id"))
                    elif ent.get("source_id") is not None:
                        legacy_row_id = int(ent.get("source_id"))
                except (TypeError, ValueError):
                    legacy_row_id = None
                ent2 = {
                    "type": "expand_and_locate",
                    "target": "card",
                    "record_id": canon,
                    "title": title or ent.get("title", ""),
                    "plan_id": pid,
                    "plan_name": self._plan_display_name(plan_tree, pid) if pid else "未计划",
                    "card_id": canon,
                    "merged_from_legacy": t,
                    # 前端钻进类型列表后，列表行 data-bug-id 为源表 id；合并后 record_id 为卡片 id，须用此项高亮具体行
                    "legacy_row_id": legacy_row_id,
                }
                merge_entry(canon, self._grep_nav_target_priority("card"), ent2)
            else:
                merge_entry(canon, pri, ent)

        return merged

    def _plan_branch_ids_from_tree(
        self, plan_tree: Optional[Dict[str, Any]], root_plan_id: Any
    ) -> Optional[set]:
        """当前迭代 scope：root 及其子树内所有 plan_id（用于导航排序，优先展示本迭代内命中）。"""
        if not plan_tree or root_plan_id is None or root_plan_id == "":
            return None
        try:
            rid = int(root_plan_id)
        except (TypeError, ValueError):
            return None
        pm = plan_tree.get("plan_map") or {}
        root = pm.get(rid)
        ids: set = set()

        def dfs(node: Dict[str, Any]) -> None:
            pid = node.get("id")
            if pid is not None:
                try:
                    ids.add(int(pid))
                except (TypeError, ValueError):
                    pass
            for ch in node.get("children") or []:
                if isinstance(ch, dict):
                    dfs(ch)

        if root and isinstance(root, dict):
            dfs(root)
        else:
            ids.add(rid)
        return ids if ids else {rid}

    def _finalize_grep_navigation_items(
        self,
        items: List[Dict[str, Any]],
        plan_tree: Optional[Dict[str, Any]],
        scope_plan_id: Any,
    ) -> List[Dict[str, Any]]:
        """去重后排序：优先当前 plan_id 子树内条目，再限幅（GREP_NAVIGATION_MAX_ITEMS）。"""
        try:
            max_n = int(os.getenv("GREP_NAVIGATION_MAX_ITEMS", "12") or "12")
        except ValueError:
            max_n = 12
        max_n = max(1, min(max_n, 50))

        branch = self._plan_branch_ids_from_tree(plan_tree, scope_plan_id)

        def _pid_int(entry: Dict[str, Any]) -> int:
            raw = entry.get("plan_id")
            if raw is None or raw == "":
                return -1
            try:
                return int(raw)
            except (TypeError, ValueError):
                return -1

        def _in_scope(entry: Dict[str, Any]) -> int:
            if branch is None:
                return 0
            p = _pid_int(entry)
            if p < 0:
                return 1
            return 0 if p in branch else 1

        def sort_key(entry: Dict[str, Any]):
            title = (entry.get("title") or "").strip()
            return (_in_scope(entry), _pid_int(entry), title)

        items.sort(key=sort_key)
        if len(items) <= max_n:
            return items
        return items[:max_n]

    def _build_grep_navigation_items(
        self,
        plan_tree: Optional[Dict[str, Any]],
        grep_target: str,
        badcase_list: List[Dict[str, Any]],
        bug_list: List[Dict[str, Any]],
        testcase_list: List[Dict[str, Any]],
        card_list: Optional[List[Dict[str, Any]]] = None,
        scope_plan_id: Any = None,
        plan_entity_list: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        生成前端「点击跳转」列表项；与 bug 一致带 type=expand_and_locate，并统一 record_id/title，
        同时保留 bug_id/bug_title 兼容旧前端。card 的 record_id 为 Card.id，target=card。
        target=all 时同一卡片会在多类列表中重复出现，这里按 record_id 合并，优先保留 target=card。
        """
        gt = (grep_target or 'all').strip().lower()
        if gt == "plan":
            out_plan: List[Dict[str, Any]] = []
            for pl in plan_entity_list or []:
                pid = pl.get("id")
                if pid is None:
                    continue
                try:
                    rid = int(pid)
                except (TypeError, ValueError):
                    continue
                title = (pl.get("name") or pl.get("title") or "").strip()
                pname = self._plan_display_name(plan_tree, rid) or title or f"Plan #{rid}"
                out_plan.append(
                    {
                        "type": "expand_and_locate",
                        "target": "plan",
                        "record_id": rid,
                        "title": title or pname,
                        "plan_id": rid,
                        "plan_name": pname,
                    }
                )
            return self._finalize_grep_navigation_items(out_plan, plan_tree, scope_plan_id)
        raw_items: List[Dict[str, Any]] = []
        card_list = card_list or []
        # record_id -> (priority, entry) 取最优一条
        best_by_rid: Dict[int, Tuple[int, Dict[str, Any]]] = {}

        def _nav_push(entry: Dict[str, Any]) -> None:
            rid = entry.get("record_id")
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                return
            pri = self._grep_nav_target_priority(str(entry.get("target") or ""))
            if rid_int not in best_by_rid or pri < best_by_rid[rid_int][0]:
                best_by_rid[rid_int] = (pri, entry)

        def _normalize_nav_plan_id(raw: Any) -> Any:
            """None / 0 / '' 视为未计划，仍要进导航（否则未计划 Bug 点击查询不到、navigation 为空）。"""
            if raw is None or raw == '':
                return None
            try:
                n = int(raw)
                return n if n > 0 else None
            except (TypeError, ValueError):
                return None

        def append_bug(bug: Dict[str, Any]) -> None:
            pid = _normalize_nav_plan_id(bug.get('plan_id'))
            title = (bug.get('title') or '').strip()
            card_id = bug.get('card_id') or bug.get('cardId')
            bid = bug.get('id')
            # record_id 必须用源 Bug.id：同一卡片下多条 Bug 时若用 card_id，前端列表 data-bug-id 重复会导致高亮永远落在第一行
            rid = bid
            if rid is None:
                return
            _nav_push({
                'type': 'expand_and_locate',
                'target': 'bug',
                'record_id': rid,
                'title': title,
                'plan_id': pid,
                'plan_name': self._plan_display_name(plan_tree, pid) if pid else '未计划',
                'card_id': card_id,
                'bug_id': bid,
                'bug_title': title,
            })

        def append_badcase(bc: Dict[str, Any]) -> None:
            pid = _normalize_nav_plan_id(bc.get('plan_id'))
            title = (bc.get('title') or '').strip()
            card_id = bc.get('card_id') or bc.get('cardId')
            src_id = bc.get('id')
            rid = src_id
            if rid is None:
                return
            _nav_push({
                'type': 'expand_and_locate',
                'target': 'badcase',
                'record_id': rid,
                'title': title,
                'plan_id': pid,
                'plan_name': self._plan_display_name(plan_tree, pid) if pid else '未计划',
                'card_id': card_id,
                'source_id': src_id,
            })

        def append_tc(tc: Dict[str, Any]) -> None:
            pid = _normalize_nav_plan_id(tc.get('plan_id'))
            title = (tc.get('title') or '').strip()
            card_id = tc.get('card_id') or tc.get('cardId')
            src_id = tc.get('id')
            rid = src_id
            if rid is None:
                return
            _nav_push({
                'type': 'expand_and_locate',
                'target': 'testcase',
                'record_id': rid,
                'title': title,
                'plan_id': pid,
                'plan_name': self._plan_display_name(plan_tree, pid) if pid else '未计划',
                'card_id': card_id,
                'source_id': src_id,
            })

        def append_card(card: Dict[str, Any]) -> None:
            pid = _normalize_nav_plan_id(card.get('plan_id'))
            cid = card.get('card_id') if card.get('card_id') is not None else card.get('id')
            title = (card.get('title') or '').strip()
            if cid is None:
                return
            try:
                rid = int(cid)
            except (TypeError, ValueError):
                return
            _nav_push({
                'type': 'expand_and_locate',
                'target': 'card',
                'record_id': rid,
                'title': title,
                'plan_id': pid,
                'plan_name': self._plan_display_name(plan_tree, pid) if pid else '未计划',
                'card_id': rid,
            })

        if gt in ('bug', 'all'):
            for b in bug_list or []:
                append_bug(b)
        if gt in ('badcase', 'all'):
            for bc in badcase_list or []:
                append_badcase(bc)
        if gt in ('testcase', 'all'):
            for tc in testcase_list or []:
                append_tc(tc)
        # 任意 target：卡片层关键词命中也进入导航（与源表命中合并去重）
        for c in card_list:
            append_card(c)

        best_by_rid = self._collapse_navigation_merge_keys(best_by_rid, card_list, plan_tree)

        for _rid in sorted(best_by_rid.keys()):
            raw_items.append(best_by_rid[_rid][1])
        return self._finalize_grep_navigation_items(raw_items, plan_tree, scope_plan_id)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从计划名称中提取关键词"""
        if not text:
            return []
        
        # 简单分词（可替换为 jieba 等分词工具）
        keywords = []
        common_words = ['功能', '测试', '计划', '项目', '任务', '需求']
        
        for word in text:
            if len(word) >= 2 and word not in common_words:
                keywords.append(word)
        
        return keywords[:5]  # 最多5个
    
    def _infer_business_domain(self, plan_name: str) -> str:
        """根据计划名称推断业务域"""
        plan_name_lower = plan_name.lower()
        
        domain_keywords = {
            '登录': ['登录', '注册', '账号', '密码', 'login', 'auth'],
            '商品': ['商品', '商城', '商哆', '购物', 'product', 'shop'],
            '支付': ['支付', '订单', '结算', 'payment', 'order'],
            '搜索': ['搜索', '查询', 'search', 'query'],
            '个人中心': ['个人', '用户', '中心', 'profile', 'user']
        }
        
        for domain, keywords in domain_keywords.items():
            for keyword in keywords:
                if keyword in plan_name_lower:
                    return domain
        
        return '通用'
    
    def _normalize_keywords_for_match(self, keywords: str) -> List[str]:
        """
        人类式关键词拆分：支持「雪碧和七喜」等拆成多词；**与库检索配合时默认 OR**（任一词命中），
        需整句各词都命中时设 GREP_KEYWORDS_MATCH_MODE=and。
        按 和、与、的、为、空格 拆分，去掉停用字，保留有意义的词。
        """
        if not keywords or not keywords.strip():
            return []
        import re
        # 统一用空格分隔：把 "和" "与" "的" "为" 当分隔符
        text = re.sub(r'[和与的为]', ' ', keywords.strip())
        # 再按空格拆
        parts = [p.strip() for p in text.split() if p.strip()]
        # 口语里常写“测试用2”，实际标题常是“测试用例2”，这里做轻量规范化
        normalized_parts: List[str] = []
        for p in parts:
            np = re.sub(r'^测试用(?=\d)', '测试用例', p)
            normalized_parts.append(np)
        # 去掉纯停用字（单字且为常见连接/助词）
        stop = {'的', '为', '与', '和', '或', '及', '、', '，'}
        terms = [p for p in normalized_parts if p not in stop and (len(p) > 1 or p not in stop)]
        # FC/自然语言常写「登录相关的」「支付相关」：整段很少出现在标题里，去掉口语后缀再参与 AND，避免误 0 命中
        out: List[str] = []
        seen = set()
        for t in terms:
            stem = t
            for suf in ("相关的", "相关", "等问题", "问题"):
                if len(stem) > len(suf) + 1 and stem.endswith(suf):
                    stem = stem[: -len(suf)].strip()
                    break
            if not stem:
                stem = t
            if stem not in seen:
                seen.add(stem)
                out.append(stem)
        return out[:10]  # 最多 10 个词，避免过长

    def _grep_keyword_match_mode(self) -> str:
        """默认 or；GREP_KEYWORDS_MATCH_MODE=and 为逐词 AND。其它取值视为 or。"""
        m = (os.getenv("GREP_KEYWORDS_MATCH_MODE") or "or").strip().lower()
        return "and" if m == "and" else "or"

    def _apply_title_ilike_keywords(self, query, column, keyword_list: List[str]):
        if not keyword_list:
            return query
        mode = self._grep_keyword_match_mode()
        if mode == "and":
            for kw in keyword_list:
                query = query.filter(column.ilike(f"%{kw}%"))
        else:
            query = query.filter(or_(*[column.ilike(f"%{kw}%") for kw in keyword_list]))
        return query

    def _apply_card_title_desc_ilike(self, query, card_model, keyword_list: List[str]):
        """Card.title / Card.description：默认 OR；AND 时每词须在标题或描述其一命中。"""
        if not keyword_list:
            return query
        title_c = card_model.title
        desc_c = card_model.description
        mode = self._grep_keyword_match_mode()
        if mode == "and":
            for kw in keyword_list:
                query = query.filter(or_(title_c.ilike(f"%{kw}%"), desc_c.ilike(f"%{kw}%")))
        else:
            query = query.filter(
                or_(*[or_(title_c.ilike(f"%{kw}%"), desc_c.ilike(f"%{kw}%")) for kw in keyword_list])
            )
        return query

    def _text_matches_normalized_keywords(self, text: str, keywords: Optional[str]) -> bool:
        if not keywords or not str(keywords).strip():
            return False
        kw_list = self._normalize_keywords_for_match(keywords)
        hay = (text or "").lower()
        if not kw_list:
            return str(keywords).strip().lower() in hay
        mode = self._grep_keyword_match_mode()
        if mode == "and":
            return all(kw.lower() in hay for kw in kw_list)
        return any(kw.lower() in hay for kw in kw_list)
    
    async def _get_badcase_list(self, project_id: str, keywords: str = None, status: str = None, plan_id: str = None) -> List[Dict[str, Any]]:
        """逐行定位引擎（优化版）"""
        from app import db, BadCase, BadCaseStatus
        
        query = db.session.query(BadCase).filter_by(project_id=project_id)
        
        # 按 plan_id 过滤：只查当前迭代计划下的记录（人类式先看本计划再判断）
        if plan_id:
            try:
                pid = int(plan_id)
                query = query.filter(BadCase.plan_id == pid)
                print(f"[GREP] 限定计划 plan_id={pid}")
            except (ValueError, TypeError):
                pass
        
        # 按 status 过滤
        if status:
            # 标准化 status 值
            status_map = {
                '已关闭': 'closed', '关闭': 'closed', 'closed': 'closed',
                '新建': 'new', '新': 'new', 'new': 'new',
                '待处理': 'pending', 'pending': 'pending',
                '已解决': 'resolved', '解决': 'resolved', 'resolved': 'resolved',
                '已重新打开': 'reopened', '重新打开': 'reopened', 'reopened': 'reopened',
            }
            normalized_status = status_map.get(status.lower(), status.lower())
            try:
                status_enum = BadCaseStatus(normalized_status)
                # SQLite 不支持枚举类型，使用字符串值
                query = query.filter(BadCase.status == status_enum.value)
                print(f"[GREP] 按 status 过滤: {normalized_status}")
            except ValueError:
                print(f"[GREP] 无效的 status 值: {status}")
        
        # 关键词：拆分后默认 OR（任一词命中 title）；GREP_KEYWORDS_MATCH_MODE=and 时逐词 AND
        keyword_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_query_all = not keyword_list and (not keywords or keywords.strip() == '' or keywords == '*')
        if not is_query_all and keyword_list:
            query = self._apply_title_ilike_keywords(query, BadCase.title, keyword_list)
            print(f"[GREP] BadCase 关键词 mode={self._grep_keyword_match_mode()}: {keyword_list} (原: {keywords})")
        elif not is_query_all and keywords and not keyword_list:
            # 拆分后为空（全是停用字）则整句匹配
            query = query.filter(BadCase.title.ilike(f'%{keywords.strip()}%'))
            print(f"[GREP] 单关键词搜索: {keywords}")
        
        # 查询全部时不限制数量，否则限制20条
        if is_query_all:
            print(f"[GREP] 查询所有 BadCase，project_id={project_id}")
            badcases = query.order_by(BadCase.created_at.desc()).limit(100).all()
        else:
            badcases = query.order_by(BadCase.created_at.desc()).limit(20).all()
        
        result = []
        for bc in badcases:
            result.append({
                'id': bc.id,
                'title': bc.title,
                'status': bc.status.value if hasattr(bc.status, 'value') else bc.status,
                'priority': bc.priority,
                'assignee': bc.assignee,  # BadCase 使用 assignee（字符串），不是 assignee_id
                'plan_id': bc.plan_id,
                'created_at': bc.created_at.isoformat() if bc.created_at else None,
                'business_scenario': self._infer_business_scenario(bc.title, keywords),
                'extracted_keywords': self._extract_keywords(bc.title),
                'keyword_match': keywords and keywords in bc.title
            })
            print(f"[GREP] BadCase ID={bc.id}, plan_id={bc.plan_id}")
        
        return result
    
    async def _get_bug_list(self, project_id: str, keywords: str = None, status: str = None, plan_id: str = None) -> List[Dict[str, Any]]:
        """Bug定位引擎（优化版），支持 plan_id 与关键词拆分模糊匹配"""
        from app import db, Bug, BugStatus
        
        try:
            project_id_int = int(project_id)
        except (ValueError, TypeError):
            project_id_int = 1
        
        print(f"[GREP] 搜索 Bug: project_id={project_id_int}, keywords={keywords}, status={status}, plan_id={plan_id}")
        
        query = db.session.query(Bug).filter_by(project_id=project_id_int)
        
        # 按 plan_id 过滤：只查当前迭代计划下的记录
        if plan_id:
            try:
                pid = int(plan_id)
                query = query.filter(Bug.plan_id == pid)
                print(f"[GREP] 限定计划 plan_id={pid}")
            except (ValueError, TypeError):
                pass
        
        # 按 status 过滤
        if status:
            # 标准化 status 值
            status_map = {
                '已关闭': 'closed', '关闭': 'closed', 'closed': 'closed',
                '新建': 'new', '新': 'new', 'new': 'new',
                '已分配': 'assigned', '分配': 'assigned', 'assigned': 'assigned',
                '进行中': 'in_progress', '处理中': 'in_progress', 'in_progress': 'in_progress',
                '已解决': 'resolved', '解决': 'resolved', 'resolved': 'resolved',
                '已重新打开': 'reopened', '重新打开': 'reopened', 'reopened': 'reopened',
            }
            normalized_status = status_map.get(status.lower(), status.lower())
            try:
                status_enum = BugStatus(normalized_status)
                # SQLite 不支持枚举类型，使用字符串值
                query = query.filter(Bug.status == status_enum.value)
                print(f"[GREP] 按 status 过滤: {normalized_status}")
            except ValueError:
                print(f"[GREP] 无效的 status 值: {status}")
        
        keyword_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_query_all = not keyword_list and (not keywords or keywords.strip() == '' or keywords == '*')
        if not is_query_all and keyword_list:
            query = self._apply_title_ilike_keywords(query, Bug.title, keyword_list)
            print(f"[GREP] Bug 关键词 mode={self._grep_keyword_match_mode()}: {keyword_list}")
        elif not is_query_all and keywords and not keyword_list:
            query = query.filter(Bug.title.ilike(f'%{keywords.strip()}%'))
        
        if is_query_all:
            print(f"[GREP] 查询所有 Bug，project_id={project_id_int}")
            bugs = query.order_by(Bug.created_at.desc()).limit(100).all()
        else:
            bugs = query.order_by(Bug.created_at.desc()).limit(20).all()
        
        print(f"[GREP] 找到 {len(bugs)} 个 Bug")
        
        result = []
        for bug in bugs:
            result.append({
                'id': bug.id,
                'title': bug.title,
                'status': bug.status.value if hasattr(bug.status, 'value') else bug.status,
                'severity': bug.severity,
                'priority': getattr(bug, 'priority', 'medium'),
                'assignee_id': bug.assignee_id,
                'plan_id': bug.plan_id,
                'card_id': getattr(bug, 'card_id', None),
                'created_at': bug.created_at.isoformat() if bug.created_at else None,
                'business_scenario': self._infer_business_scenario(bug.title, keywords),
                'extracted_keywords': self._extract_keywords(bug.title),
                'keyword_match': keywords and keywords in bug.title
            })
        
        return result
    
    async def _get_testcase_list(self, project_id: str, keywords: str = None, status: str = None, plan_id: str = None) -> List[Dict[str, Any]]:
        """测试用例定位，支持 plan_id 与关键词拆分模糊匹配"""
        from app import db, TestCase
        try:
            project_id_int = int(project_id)
        except (ValueError, TypeError):
            project_id_int = 1
        query = db.session.query(TestCase).filter_by(project_id=project_id_int)
        if plan_id:
            try:
                query = query.filter(TestCase.plan_id == int(plan_id))
            except (ValueError, TypeError):
                pass
        if status:
            status_map = {'草稿': 'draft', 'draft': 'draft', '评审': 'review', 'review': 'review', '生效': 'active', 'active': 'active', '归档': 'archived', 'archived': 'archived'}
            norm = status_map.get(status.strip().lower(), status.strip().lower())
            try:
                from app import TestCaseStatus
                status_enum = TestCaseStatus(norm)
                query = query.filter(TestCase.status == status_enum.value)
            except (ValueError, TypeError):
                query = query.filter(TestCase.status == norm)
        keyword_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_query_all = not keyword_list and (not keywords or keywords.strip() == '' or keywords == '*')
        if not is_query_all and keyword_list:
            query = self._apply_title_ilike_keywords(query, TestCase.title, keyword_list)
        elif not is_query_all and keywords and not keyword_list:
            query = query.filter(TestCase.title.ilike(f'%{keywords.strip()}%'))
        testcases = query.order_by(TestCase.created_at.desc()).limit(100 if is_query_all else 20).all()
        result = []
        for tc in testcases:
            result.append({
                'id': tc.id,
                'title': tc.title,
                'status': tc.status.value if hasattr(tc.status, 'value') else str(tc.status),
                'plan_id': tc.plan_id,
                'created_at': tc.created_at.isoformat() if tc.created_at else None,
                'business_scenario': self._infer_business_scenario(tc.title, keywords),
            })
        return result

    async def _get_card_list(
        self, project_id: str, keywords: str = None, plan_id: str = None
    ) -> List[Dict[str, Any]]:
        """统一卡片层 Card：按 title / description 检索（多词默认 OR）。"""
        from app import db, Card

        try:
            project_id_int = int(project_id)
        except (ValueError, TypeError):
            project_id_int = 1

        query = db.session.query(Card).filter(Card.project_id == project_id_int)
        if plan_id:
            try:
                query = query.filter(Card.plan_id == int(plan_id))
            except (ValueError, TypeError):
                pass

        keyword_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_query_all = not keyword_list and (not keywords or keywords.strip() == '' or keywords == '*')
        if not is_query_all and keyword_list:
            query = self._apply_card_title_desc_ilike(query, Card, keyword_list)
            print(f"[GREP] Card 关键词 mode={self._grep_keyword_match_mode()}: {keyword_list}")
        elif not is_query_all and keywords and not keyword_list:
            k = keywords.strip()
            query = query.filter(or_(Card.title.ilike(f"%{k}%"), Card.description.ilike(f"%{k}%")))

        limit_n = 100 if is_query_all else 20
        cards = query.order_by(Card.updated_at.desc()).limit(limit_n).all()
        out: List[Dict[str, Any]] = []
        for c in cards:
            out.append({
                'id': c.id,
                'title': c.title,
                'description': (c.description or '')[:800],
                'plan_id': c.plan_id,
                'source_type': c.source_type,
                'source_id': c.source_id,
                'card_id': c.id,
                'created_at': c.created_at.isoformat() if c.created_at else None,
            })
        print(f"[GREP] Card 命中 {len(out)} 条")
        return out
    
    @staticmethod
    def _plan_records_root_name(plan_records_tree: Optional[Dict[str, Any]]) -> Optional[str]:
        if not plan_records_tree or not isinstance(plan_records_tree, dict):
            return None
        p = plan_records_tree.get("plan")
        if isinstance(p, dict):
            name = (p.get("name") or "").strip()
            return name or None
        return None

    async def _analyze_associations(
        self,
        keywords: str,
        plan_tree: Dict[str, Any],
        badcase_list: List[Dict[str, Any]],
        bug_list: List[Dict[str, Any]],
        testcase_list: List[Dict[str, Any]] = None,
        card_list: List[Dict[str, Any]] = None,
        evidence: Dict[str, Any] = None,
        ui_locale: Optional[str] = None,
        plan_records_tree: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """分析关联关系（含 BadCase/Bug/TestCase/Card）"""
        testcase_list = testcase_list or []
        card_list = card_list or []
        badcase_analysis = []
        bug_location = []
        testcase_location = []
        card_location = []
        plan_attribution = []
        plan_map = plan_tree.get('plan_map', {})

        kw_norm = self._normalize_keywords_for_match(keywords) if keywords else []
        is_query_all = (not kw_norm) and (
            not keywords or str(keywords).strip() == '' or str(keywords).strip() == '*'
        )

        def _related_title(keywords_arg: Optional[str], *parts: str) -> bool:
            if is_query_all:
                return True
            hay = " ".join(p for p in parts if p)
            return self._text_matches_normalized_keywords(hay, keywords_arg)

        for bc in badcase_list:
            is_related = _related_title(
                keywords,
                bc.get('title') or '',
                bc.get('card_title') or '',
            )
            analysis_item = {
                'id': bc['id'],
                'title': bc['title'],
                'business_scenario': bc.get('business_scenario', ''),
                'keywords': bc.get('extracted_keywords', []),
                'severity': self._assess_severity(bc),
                'related_to_evidence': is_related,
                'plan_id': bc.get('plan_id'),
                'current_plan_id': bc.get('plan_id')
            }
            print(f"[GREP-ANALYSIS] BadCase ID={bc['id']}, plan_id={bc.get('plan_id')}, item.plan_id={analysis_item['plan_id']}")
            badcase_analysis.append(analysis_item)

        for bug in bug_list:
            is_related = _related_title(
                keywords,
                bug.get('title') or '',
                bug.get('card_title') or '',
            )
            plan_id = bug.get('plan_id')
            plan_name = plan_map.get(plan_id, {}).get('name', '') if plan_id else ''

            bug_location.append({
                'id': bug['id'],
                'title': bug['title'],
                'business_scenario': bug.get('business_scenario', ''),
                'related_badcases': [],
                'related_to_evidence': is_related,
                'current_plan_id': plan_id,
                'plan_name': plan_name
            })

        for tc in testcase_list:
            is_related = _related_title(
                keywords,
                tc.get('title') or '',
                tc.get('card_title') or '',
            )
            plan_id = tc.get('plan_id')
            plan_name = plan_map.get(plan_id, {}).get('name', '') if plan_id else ''
            testcase_location.append({
                'id': tc['id'],
                'title': tc['title'],
                'business_scenario': tc.get('business_scenario', ''),
                'related_to_evidence': is_related,
                'current_plan_id': plan_id,
                'plan_name': plan_name
            })

        for c in card_list:
            is_related = _related_title(
                keywords,
                c.get('title') or '',
                c.get('description') or '',
            )
            plan_id = c.get('plan_id')
            plan_name = plan_map.get(plan_id, {}).get('name', '') if plan_id else ''
            card_location.append({
                'id': c['id'],
                'title': c['title'],
                'business_scenario': '',
                'related_to_evidence': is_related,
                'current_plan_id': plan_id,
                'plan_name': plan_name
            })

        try:
            tp = int(plan_tree.get("total_plans") or 0)
        except (TypeError, ValueError):
            tp = 0
        if tp <= 0 and isinstance(plan_tree.get("plans"), list):
            tp = len(plan_tree["plans"])

        try:
            summary = grep_generate_locate_summary(
                ui_locale,
                keywords=keywords,
                badcase_count=len(badcase_list),
                bug_count=len(bug_list),
                testcase_count=len(testcase_list),
                card_count=len(card_list),
                related_badcase_count=sum(1 for bc in badcase_analysis if bc['related_to_evidence']),
                related_bug_count=sum(1 for bug in bug_location if bug['related_to_evidence']),
                related_testcase_count=sum(1 for tc in testcase_location if tc['related_to_evidence']),
                related_card_count=sum(1 for x in card_location if x['related_to_evidence']),
                attribution_count=len(plan_attribution),
                bug_location=bug_location,
                total_plans=tp,
                plan_material_loaded=plan_records_tree is not None,
                plan_material_root_name=self._plan_records_root_name(plan_records_tree),
            )
            summary = enrich_grep_observation_nl_with_plan_names(
                summary,
                {"plan_tree": plan_tree},
                ui_locale,
            )
        except Exception as sum_e:
            print(f"[GREP] ⚠️ 摘要生成失败（已降级，仍返回定位数据）: {sum_e}")
            nb, ng, nt = len(badcase_list), len(bug_list), len(testcase_list)
            if is_english_locale(ui_locale):
                summary = f"🐛 Located: BadCase={nb}, Bug={ng}, Test case={nt}."
            else:
                summary = f"🐛 定位摘要降级：BadCase {nb} 条、Bug {ng} 条、测试用例 {nt} 条。"
            try:
                summary = enrich_grep_observation_nl_with_plan_names(
                    summary,
                    {"plan_tree": plan_tree},
                    ui_locale,
                )
            except Exception:
                pass

        return {
            'badcase_analysis': badcase_analysis,
            'bug_location': bug_location,
            'testcase_location': testcase_location,
            'card_location': card_location,
            'plan_attribution': plan_attribution,
            'summary': summary
        }
    
    def _is_related_to_keywords(self, text: str, keywords: str) -> bool:
        """判断文本是否与关键词相关"""
        if not keywords:
            return False
        return keywords.lower() in text.lower()
    
    def _infer_business_scenario(self, title: str, keywords: str) -> str:
        """推断业务场景"""
        title_lower = title.lower()
        
        # 常见业务场景关键词
        scenarios = {
            '登录': ['登录', 'login', '认证', 'auth'],
            '商品': ['商品', 'product', '价格', 'price', '雪碧', '可乐'],
            '支付': ['支付', 'payment', '订单', 'order'],
            '搜索': ['搜索', 'search', '查询', 'query']
        }
        
        for scenario, kws in scenarios.items():
            if any(kw in title_lower for kw in kws):
                return f"{scenario}模块"
        
        return "未知业务场景"
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取（可以后续使用NLP优化）
        keywords = []
        common_keywords = ['登录', '商品', '支付', '搜索', '价格', '订单', '用户']
        
        text_lower = text.lower()
        for kw in common_keywords:
            if kw in text_lower:
                keywords.append(kw)
        
        return keywords if keywords else [text[:10]]  # 如果没有匹配，返回标题前10个字
    
    def _assess_severity(self, item: Dict[str, Any]) -> str:
        """评估严重程度"""
        priority = item.get('priority', '')
        status = item.get('status', '')
        
        if priority in ['紧急', 'critical', 'high']:
            return '高'
        elif status in ['新建', 'new']:
            return '中'
        else:
            return '低'
    
    def _are_related(self, text1: str, text2: str) -> bool:
        """判断两个文本是否相关"""
        # 简单的相似度判断
        keywords1 = set(self._extract_keywords(text1))
        keywords2 = set(self._extract_keywords(text2))
        return len(keywords1 & keywords2) > 0
    
    def _recommend_plan(
        self,
        business_scenario: str,
        plan_tree: Dict[str, Any],
        keywords: str
    ) -> Dict[str, Any]:
        """根据业务场景推荐计划"""
        # 遍历进行中的计划
        for plan in plan_tree.get('in_progress', []):
            plan_name_lower = plan['name'].lower()
            
            # 如果计划名称包含业务场景关键词
            if business_scenario and any(
                kw in plan_name_lower
                for kw in business_scenario.replace('模块', '').split()
            ):
                return plan
            
            # 如果计划名称包含搜索关键词
            if keywords and keywords.lower() in plan_name_lower:
                return plan
            
            # 如果是bug类型计划，优先考虑
            if plan['type'] == 'bug' and keywords:
                return plan
        
        return None
    
    async def _three_way_association(self, project_id: str, keywords: str) -> List[Dict[str, Any]]:
        """
        三向关联分析：BadCase ↔ Bug ↔ TestCase
        
        核心逻辑：
        1. BadCase 可能关联多个 Bug
        2. Bug 可能关联多个 BadCase
        3. 测试用例通过BadCase间接关联Bug
        """
        from app import db, BadCase, Bug
        
        associations = []
        
        # 获取所有BadCase和Bug
        badcases = db.session.query(BadCase).filter_by(project_id=project_id).all()
        bugs = db.session.query(Bug).filter_by(project_id=project_id).all()
        
        for badcase in badcases:
            if keywords and keywords not in badcase.title:
                continue
            
            # 查找相关Bug（通过标题相似度）
            related_bugs = []
            for bug in bugs:
                if self._are_related(badcase.title, bug.title):
                    related_bugs.append({
                        'id': bug.id,
                        'title': bug.title,
                        'status': bug.status,
                        'priority': bug.priority
                    })
            
            if related_bugs:
                associations.append({
                    'badcase': {
                        'id': badcase.id,
                        'title': badcase.title,
                        'type': badcase.type
                    },
                    'related_bugs': related_bugs,
                    'association_strength': len(related_bugs),
                    'recommendation': f"建议关联 {len(related_bugs)} 个Bug"
                })
        
        return associations
    
    async def _generate_comparison(self, project_id: str, keywords: str) -> Dict[str, Any]:
        """
        生成修改前后对比（Markdown格式）
        
        对比维度：
        1. 计划归属变化
        2. 状态变化
        3. 优先级调整
        4. 关联关系变化
        """
        from app import db, BadCase, Bug
        import datetime
        
        # 模拟修改前后对比（实际应从历史记录中获取）
        comparison = {
            'timestamp': datetime.datetime.now().isoformat(),
            'changes': [],
            'markdown': ''
        }
        
        badcases = db.session.query(BadCase).filter_by(project_id=project_id).all()
        
        markdown_lines = [
            f"# 缺陷修改前后对比\n",
            f"**生成时间**: {comparison['timestamp']}\n",
            f"**关键词**: {keywords}\n",
            "\n---\n\n"
        ]
        
        for badcase in badcases:
            if keywords and keywords not in badcase.title:
                continue
            
            # 模拟变更（实际应查询历史）
            change = {
                'badcase_id': badcase.id,
                'title': badcase.title,
                'changes': [
                    {'field': '状态', 'before': '新建', 'after': badcase.status},
                    {'field': '优先级', 'before': 'P3', 'after': badcase.priority}
                ]
            }
            comparison['changes'].append(change)
            
            markdown_lines.append(f"## BadCase: {badcase.title}\n\n")
            markdown_lines.append("| 字段 | 修改前 | 修改后 |\n")
            markdown_lines.append("|------|------|------|\n")
            for ch in change['changes']:
                markdown_lines.append(f"| {ch['field']} | {ch['before']} | {ch['after']} |\n")
            markdown_lines.append("\n")
        
        comparison['markdown'] = ''.join(markdown_lines)
        return comparison