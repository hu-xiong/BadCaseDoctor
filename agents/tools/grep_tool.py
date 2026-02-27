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
            description="缺陷定位工具：模拟人类阅读习惯，精准定位BadCase/Bug/测试用例的归属关系和业务场景。"
                         "必须参数：keywords(关键词), project_id(项目ID), target(分析目标：bug/badcase/all)。"
                         "重要：根据用户意图设置target参数 - 查询Bug时用target=bug，查询BadCase时用target=badcase"
        )
    
    async def execute(
        self,
        keywords: str = None,
        project_id: str = None,
        plan_context: str = None,
        evidence: Dict[str, Any] = None,
        mode: str = "locate",  # locate/associate/compare
        target: str = "all",  # 新增：all/bug/badcase - 分析目标
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
            **kwargs: 其他参数
            
        Returns:
            定位分析结果（包含思考过程）
        """
        print(f"[GREP] 🔍 开始定位 (keywords={keywords}, target={target})")
        
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
                    # 【阶段1】数据库查询
                    plan_tree = await self._get_plan_tree(project_id)
                    
                    badcase_list = []
                    bug_list = []
                    if target in ['all', 'badcase']:
                        badcase_list = await self._get_badcase_list(project_id, keywords)
                    if target in ['all', 'bug']:
                        bug_list = await self._get_bug_list(project_id, keywords)
                    
                    # 【阶段2】分析关联
                    analysis_result = await self._analyze_associations(
                        keywords=keywords,
                        plan_tree=plan_tree,
                        badcase_list=badcase_list,
                        bug_list=bug_list,
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
                        'badcase_analysis': analysis_result['badcase_analysis'],
                        'bug_location': analysis_result['bug_location'],
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
    
    async def _get_badcase_list(self, project_id: str, keywords: str = None) -> List[Dict[str, Any]]:
        """逐行定位引擎（优化版）"""
        from app import db, BadCase
        
        query = db.session.query(BadCase).filter_by(project_id=project_id)
        
        if keywords:
            query = query.filter(BadCase.title.ilike(f'%{keywords}%'))
        
        # 限制返回数量，避免处理过多数据
        badcases = query.order_by(BadCase.created_at.desc()).limit(20).all()
        
        result = []
        for bc in badcases:
            result.append({
                'id': bc.id,
                'title': bc.title,
                'status': bc.status.value if hasattr(bc.status, 'value') else bc.status,
                'priority': bc.priority,
                'assignee_id': bc.assignee_id,
                'plan_id': bc.plan_id,
                'created_at': bc.created_at.isoformat() if bc.created_at else None,
                'business_scenario': self._infer_business_scenario(bc.title, keywords),
                'extracted_keywords': self._extract_keywords(bc.title),
                'keyword_match': keywords and keywords in bc.title
            })
        
        return result
    
    async def _get_bug_list(self, project_id: str, keywords: str = None) -> List[Dict[str, Any]]:
        """Bug定位引擎（优化版）"""
        from app import db, Bug
        
        query = db.session.query(Bug).filter_by(project_id=project_id)
        
        if keywords:
            query = query.filter(Bug.title.ilike(f'%{keywords}%'))
        
        bugs = query.order_by(Bug.created_at.desc()).limit(20).all()
        
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
    
    async def _analyze_associations(
        self,
        keywords: str,
        plan_tree: Dict[str, Any],
        badcase_list: List[Dict[str, Any]],
        bug_list: List[Dict[str, Any]],
        evidence: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """分析关联关系（优化版）"""
        
        badcase_analysis = []
        bug_location = []
        plan_attribution = []
        
        # 构建 plan_id -> plan_name 映射
        plan_map = plan_tree.get('plan_map', {})
        
        # 分析 BadCase
        for bc in badcase_list:
            is_related = keywords and keywords.lower() in bc['title'].lower()
            badcase_analysis.append({
                'id': bc['id'],
                'title': bc['title'],
                'business_scenario': bc.get('business_scenario', ''),
                'keywords': bc.get('extracted_keywords', []),
                'severity': self._assess_severity(bc),
                'related_to_evidence': is_related,
                'current_plan_id': bc.get('plan_id')
            })
        
        # 分析 Bug
        for bug in bug_list:
            is_related = keywords and keywords.lower() in bug['title'].lower()
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
        
        # 生成总结
        summary = self._generate_summary(
            keywords=keywords,
            badcase_count=len(badcase_list),
            bug_count=len(bug_list),
            related_badcase_count=sum(1 for bc in badcase_analysis if bc['related_to_evidence']),
            related_bug_count=sum(1 for bug in bug_location if bug['related_to_evidence']),
            attribution_count=len(plan_attribution),
            bug_location=bug_location
        )
        
        return {
            'badcase_analysis': badcase_analysis,
            'bug_location': bug_location,
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
        bug_location: List[Dict[str, Any]] = None  # 新增参数
    ) -> str:
        """生成分析总结（人类可读）"""
        parts = []
        
        # 1. BadCase定位结果
        if badcase_count > 0:
            if related_badcase_count > 0:
                parts.append(f"🔍 定位 {related_badcase_count} 条BadCase（关键词：{keywords}）")
            else:
                parts.append(f"🔍 扫描了 {badcase_count} 条BadCase，未找到匹配 '{keywords}' 的记录")
        
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
                parts.append(f"🐛 扫描了 {bug_count} 条Bug，未找到匹配 '{keywords}' 的记录")
        
        # 3. 计划归属建议
        if attribution_count > 0:
            parts.append(f"🎯 生成 {attribution_count} 条计划归属调整建议")
        
        return '\n'.join(parts) if parts else '未找到相关缺陷'
    
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