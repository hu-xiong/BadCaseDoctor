"""
Grep Tool - 缺陷定位工具
模拟人类测试工程师的思维模式，精准定位 BadCase/Bug/测试用例的归属关系
"""
from typing import Dict, Any, List
import json
from agents.tool_registry import BaseTool


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
        super().__init__(
            name="grep",
            description="缺陷定位工具：模拟人类阅读习惯，先检索再阅读。精准定位BadCase/Bug/测试用例的归属关系和业务场景。"
                         "必须参数：project_id(项目ID)。可选：keywords(标题关键词，支持拆分模糊匹配), target(bug/badcase/testcase/all)，status，plan_id(当前迭代计划ID)。"
                         "返回 plan_tree、badcase_analysis、bug_location、testcase_location。建议先用 plan_id 限定迭代计划，再把候选记录交给大模型逐条阅读判断。"
        )
    
    async def execute(
        self,
        keywords: str = None,
        project_id: str = None,
        plan_id: str = None,  # 当前迭代计划ID，传入则只检索该计划下的记录
        plan_context: str = None,
        evidence: Dict[str, Any] = None,
        mode: str = "locate",  # locate/associate/compare
        target: str = "all",  # all/bug/badcase/testcase
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
            target: 分析目标（新增）
                - all: 分析BadCase和Bug（默认）
                - bug: 只分析Bug
                - badcase: 只分析BadCase
            status: 按状态过滤（如 "closed", "new", "pending" 等）
            **kwargs: 其他参数
            
        Returns:
            定位分析结果（包含思考过程）
        """
        print(f"[GREP] 🔍 开始定位 (keywords={keywords}, target={target}, status={status}, plan_id={plan_id})")
        
        try:
            from app import app, db, BadCase, Bug, Plan
            
            result = {
                'success': True,
                'mode': mode,
                'thinking_process': [],
                'data': {}
            }
            
            with app.app_context():
                if mode == "locate":
                    # 【阶段1】数据库查询（支持 plan_id 限定当前迭代，关键词拆分模糊匹配）
                    plan_tree = await self._get_plan_tree(project_id)

                    # 人类阅读模式：如果指定了 plan_id，则返回该计划及其子计划的树形结构，并挂载各计划下的记录（从上到下、从外到里）
                    plan_records_tree = None
                    if plan_id:
                        plan_records_tree = await self._build_plan_records_tree(project_id=project_id, root_plan_id=plan_id)
                    
                    badcase_list = []
                    bug_list = []
                    testcase_list = []
                    if target in ['all', 'badcase']:
                        badcase_list = await self._get_badcase_list(project_id, keywords, status, plan_id=plan_id)
                    if target in ['all', 'bug']:
                        bug_list = await self._get_bug_list(project_id, keywords, status, plan_id=plan_id)
                    if target in ['all', 'testcase']:
                        testcase_list = await self._get_testcase_list(project_id, keywords, status, plan_id=plan_id)
                    
                    # 【阶段2】分析关联
                    analysis_result = await self._analyze_associations(
                        keywords=keywords,
                        plan_tree=plan_tree,
                        badcase_list=badcase_list,
                        bug_list=bug_list,
                        testcase_list=testcase_list,
                        evidence=evidence
                    )
                    
                    # 【阶段3】生成对比报告
                    comparison = await self._generate_comparison(project_id, keywords)
                    
                    # 生成导航指令
                    navigation = None
                    if bug_list:
                        navigation_list = []
                        for bug in bug_list:
                            if bug.get('plan_id'):
                                # 查找计划名称
                                plan_name = ''
                                if plan_tree and 'plans' in plan_tree:
                                    for plan in plan_tree['plans']:
                                        if plan['id'] == bug.get('plan_id'):
                                            plan_name = plan['name']
                                            break
                                
                                navigation_list.append({
                                    'type': 'expand_and_locate',
                                    'target': 'bug',
                                    'bug_id': bug['id'],
                                    'plan_id': bug['plan_id'],
                                    'bug_title': bug['title'],
                                    'plan_name': plan_name
                                })
                        
                        if navigation_list:
                            navigation = navigation_list[0] if len(navigation_list) == 1 else {
                                'type': 'multiple',
                                'items': navigation_list
                            }
                            print(f"[GREP] ✅ 定位完成: {len(bug_list)}条Bug, {len(badcase_list)}条BadCase")
                    
                    result['data'] = {
                        'plan_tree': plan_tree,
                        'plan_records_tree': plan_records_tree,
                        'badcase_analysis': analysis_result['badcase_analysis'],
                        'bug_location': analysis_result['bug_location'],
                        'testcase_location': analysis_result.get('testcase_location', []),
                        'plan_attribution': analysis_result['plan_attribution'],
                        'comparison_report': comparison['markdown'],
                        'summary': analysis_result['summary'],
                        'navigation': navigation
                    }
                    
                elif mode == "associate":
                    # 三向关联模式
                    associations = await self._three_way_association(project_id, keywords)
                    result['data'] = {
                        'associations': associations,
                        'total_associations': len(associations),
                        'summary': f"共建立 {len(associations)} 组关联关系"
                    }
                    
                elif mode == "compare":
                    # 对比模式
                    comparison = await self._generate_comparison(project_id, keywords)
                    result['data'] = {
                        'comparison': comparison,
                        'markdown': comparison['markdown'],
                        'changes_count': len(comparison['changes']),
                        'summary': f"共 {len(comparison['changes'])} 项变更"
                    }
                
                return result
                
        except Exception as e:
            print(f"[GREP] ❌ 定位分析失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

    async def _build_plan_records_tree(self, project_id: str, root_plan_id: str) -> Dict[str, Any]:
        """
        构建“计划树 + 计划下记录”的阅读结构：
        - 从 root_plan_id 出发，递归包含所有子计划
        - 每个计划节点挂载 badcases/bugs/testcases（包含尽可能完整字段，便于大模型逐条阅读判断）
        """
        from app import db, Plan, BadCase, Bug, TestCase
        try:
            root_id = int(root_plan_id)
        except (ValueError, TypeError):
            return None

        # 取该项目下所有计划，构建 parent->children
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
        badcases = db.session.query(BadCase).filter(BadCase.project_id == int(project_id), BadCase.plan_id.in_(plan_ids)).all() if plan_ids else []
        bugs = db.session.query(Bug).filter(Bug.project_id == int(project_id), Bug.plan_id.in_(plan_ids)).all() if plan_ids else []
        testcases = db.session.query(TestCase).filter(TestCase.project_id == int(project_id), TestCase.plan_id.in_(plan_ids)).all() if plan_ids else []

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
                'plan_type': getattr(p, 'plan_type', None),
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

        return build_node(root_id)
    
    async def _get_plan_tree(self, project_id: str) -> Dict[str, Any]:
        """
        计划阅读器：解析迭代计划结构（优化版）
        """
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
                'type': plan.plan_type,
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
        
        return {
            'total_plans': len(plans),
            'root_plans': root_plans,
            'plans': list(plan_map.values()),  # 扁平列表便于查找
            'plan_map': plan_map,
            'business_domains': list(set(p['business_domain'] for p in plan_map.values()))
        }
    
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
        人类式关键词拆分：支持「雪碧和七喜」「雪碧 七喜」「雪碧的七喜」都拆成 [雪碧，七喜]，用于模糊 AND 匹配。
        按 和、与、的、为、空格 拆分，去掉停用字（的、为、与、和等单字连接词），保留有意义的词。
        """
        if not keywords or not keywords.strip():
            return []
        import re
        # 统一用空格分隔：把 "和" "与" "的" "为" 当分隔符
        text = re.sub(r'[和与的为]', ' ', keywords.strip())
        # 再按空格拆
        parts = [p.strip() for p in text.split() if p.strip()]
        # 去掉纯停用字（单字且为常见连接/助词）
        stop = {'的', '为', '与', '和', '或', '及', '、', '，'}
        terms = [p for p in parts if p not in stop and (len(p) > 1 or p not in stop)]
        return terms[:10]  # 最多 10 个词，避免过长
    
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
        
        # 关键词：支持拆分模糊匹配（人类式，和/与/空格拆词，每个词都匹配即可）
        keyword_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_query_all = not keyword_list and (not keywords or keywords.strip() == '' or keywords == '*')
        if not is_query_all and keyword_list:
            from sqlalchemy import and_
            for kw in keyword_list:
                query = query.filter(BadCase.title.ilike(f'%{kw}%'))
            print(f"[GREP] 拆分关键词模糊匹配: {keyword_list} (原: {keywords})")
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
        
        # 关键词：拆分模糊匹配（与 BadCase 一致）
        keyword_list = self._normalize_keywords_for_match(keywords) if keywords else []
        is_query_all = not keyword_list and (not keywords or keywords.strip() == '' or keywords == '*')
        if not is_query_all and keyword_list:
            for kw in keyword_list:
                query = query.filter(Bug.title.ilike(f'%{kw}%'))
            print(f"[GREP] Bug 拆分关键词模糊匹配: {keyword_list}")
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
            for kw in keyword_list:
                query = query.filter(TestCase.title.ilike(f'%{kw}%'))
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
    
    async def _analyze_associations(
        self,
        keywords: str,
        plan_tree: Dict[str, Any],
        badcase_list: List[Dict[str, Any]],
        bug_list: List[Dict[str, Any]],
        testcase_list: List[Dict[str, Any]] = None,
        evidence: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """分析关联关系（含 BadCase/Bug/TestCase）"""
        testcase_list = testcase_list or []
        badcase_analysis = []
        bug_location = []
        testcase_location = []
        plan_attribution = []
        plan_map = plan_tree.get('plan_map', {})
        
        # 分析 BadCase（列表已是按 keywords 过滤后的结果，故均视为匹配）
        keyword_list = [k.strip() for k in (keywords or '').split() if k.strip()] if keywords else []
        for bc in badcase_list:
            if keyword_list:
                is_related = all(kw in (bc.get('title') or '') for kw in keyword_list)
            else:
                is_related = bool(keywords and (keywords.lower() in (bc.get('title') or '').lower()))
            analysis_item = {
                'id': bc['id'],
                'title': bc['title'],
                'business_scenario': bc.get('business_scenario', ''),
                'keywords': bc.get('extracted_keywords', []),
                'severity': self._assess_severity(bc),
                'related_to_evidence': is_related,
                'plan_id': bc.get('plan_id'),  # 使用 plan_id 以便后续处理
                'current_plan_id': bc.get('plan_id')  # 保留兼容性
            }
            print(f"[GREP-ANALYSIS] BadCase ID={bc['id']}, plan_id={bc.get('plan_id')}, item.plan_id={analysis_item['plan_id']}")
            badcase_analysis.append(analysis_item)
        
        # 分析 Bug（同上，按关键词过滤后的结果均视为匹配）
        for bug in bug_list:
            if keyword_list:
                is_related = all(kw in (bug.get('title') or '') for kw in keyword_list)
            else:
                is_related = bool(keywords and (keywords.lower() in (bug.get('title') or '').lower()))
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
            keyword_list = [k.strip() for k in (keywords or '').split() if k.strip()] if keywords else []
            if keyword_list:
                is_related = all(kw in (tc.get('title') or '') for kw in keyword_list)
            else:
                is_related = bool(keywords and (keywords.lower() in (tc.get('title') or '').lower()))
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
        
        summary = self._generate_summary(
            keywords=keywords,
            badcase_count=len(badcase_list),
            bug_count=len(bug_list),
            testcase_count=len(testcase_list),
            related_badcase_count=sum(1 for bc in badcase_analysis if bc['related_to_evidence']),
            related_bug_count=sum(1 for bug in bug_location if bug['related_to_evidence']),
            related_testcase_count=sum(1 for tc in testcase_location if tc['related_to_evidence']),
            attribution_count=len(plan_attribution),
            bug_location=bug_location
        )
        
        return {
            'badcase_analysis': badcase_analysis,
            'bug_location': bug_location,
            'testcase_location': testcase_location,
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
    
    def _generate_summary(
        self,
        keywords: str,
        badcase_count: int,
        bug_count: int,
        related_badcase_count: int,
        related_bug_count: int,
        attribution_count: int,
        bug_location: List[Dict[str, Any]] = None,
        testcase_count: int = 0,
        related_testcase_count: int = 0
    ) -> str:
        """生成分析总结（人类可读）"""
        parts = []
        is_query_all = not keywords or keywords.strip() == '' or keywords == '*'
        
        if badcase_count > 0:
            if is_query_all:
                parts.append(f"🔍 找到 {badcase_count} 条BadCase")
            elif related_badcase_count > 0:
                parts.append(f"🔍 定位 {related_badcase_count} 条BadCase（关键词：{keywords}）")
            else:
                parts.append(f"🔍 定位 {badcase_count} 条BadCase（关键词：{keywords}）")
        
        # 2. Bug定位结果（显示计划名）
        if bug_count > 0:
            if related_bug_count > 0:
                # 提取第一个Bug的计划信息
                if bug_location and len(bug_location) > 0:
                    first_bug = bug_location[0]
                    plan_name = first_bug.get('plan_name', '')
                    if plan_name:
                        parts.append(f"🐛 定位 {related_bug_count} 条Bug，关键词为“{keywords}”，位于计划【{plan_name}】")
                    else:
                        parts.append(f"🐛 定位 {related_bug_count} 条Bug（关键词：{keywords}）")
                else:
                    parts.append(f"🐛 定位 {related_bug_count} 条Bug（关键词：{keywords}）")
            else:
                parts.append(f"🐛 定位 {bug_count} 条Bug（关键词：{keywords}）")
        
        if testcase_count > 0:
            if is_query_all:
                parts.append(f"📋 找到 {testcase_count} 条测试用例")
            elif related_testcase_count > 0:
                parts.append(f"📋 定位 {related_testcase_count} 条测试用例（关键词：{keywords}）")
            else:
                parts.append(f"📋 定位 {testcase_count} 条测试用例（关键词：{keywords}）")
        
        if attribution_count > 0:
            parts.append(f"🎯 生成 {attribution_count} 条计划归属调整建议")
        
        return '\n'.join(parts) if parts else '未找到相关记录'
    
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