# agents/prompts.py
"""
ReAct Prompt 工程 - Claude Code 强约束模板
适配文心一言 (Qwen) 模型

核心设计原则：
1. 长而精准 - 明确的系统上下文
2. XML 标签 - 固定输出格式
3. Good/Bad 示例 - 规范思考逻辑
4. Todo 锚定 - 保持任务焦点
"""

import json
from typing import Any, List, Dict, Union, Optional


class ReactPromptTemplates:
    """ReAct Prompt 模板库"""
    
    @staticmethod
    def think_prompt(user_input: str, available_tools: list, context: dict, todo_list: list) -> str:
        """
        THINK 阶段 Prompt - 生成结构化 Todo 列表
        
        强约束：
        - 必须返回 XML 标签包装的 JSON 数组
        - 每项 Todo 对应一个明确的工具或分析步骤
        - 最多 3-5 项，避免过度拆分
        """
        tools_description = "\n".join([
            f"  - <tool name=\"{t['name']}\">{t['description']}</tool>"
            for t in available_tools
        ])
        
        context_str = "\n".join([
            f"  - {k}: {v}"
            for k, v in context.items()
        ])
        
        return f"""你是一个任务规划专家。根据用户请求，生成一个精准的 Todo 列表。

<system>
你的角色：分析用户请求，拆分成可执行的任务步骤
约束条件：
1. 最多 5 项 Todo（保持简洁）
2. 每项 Todo 必须对应一个可用工具或明确的分析动作
3. Todo 应按逻辑顺序排列
4. 避免无效的重复调用：仔细判断是否真的需要用不同参数多次调用同一工具
5. 使用明确的、可测量的语言

关键判断规则：
- 用户请求"查询/搜索/查找Bug"时：使用database_query或grep工具查询已有数据，禁止使用browser_test
- 用户请求"测试/验证/检查功能"时：使用browser_test工具执行实际测试
- browser_test工具仅用于功能测试，不用于Bug查询

意图识别（先判断，再规划）：
1. 关键词匹配：
   - 提到"Bug/缺陷/问题/故障" → 目标是Bug，使用database_query(query_type="bug_list")
   - 提到"BadCase/测试用例/场景" → 目标是BadCase，使用database_query(query_type="badcase_list")
2. 精准定位：
   - database_query先查，找到粗粒度结果
   - grep再定位，逐行分析归属计划

重要：browser_test 工具执行一次即可完成浏览器测试，包括登录、导航、操作等所有步骤，绝对不要在一个任务中多次调用。
</system>

<user_request>
{user_input}
</user_request>

<available_tools>
{tools_description}
</available_tools>

<context>
已知信息：
{context_str if context_str else "无"}
</context>

<examples>
好的 Todo 列表：
<good_example>
<request>帮我测试登录功能并生成 Bug 列表</request>
<todo_list>
[
  "使用 browser_test 工具执行登录功能测试",
  "分析测试结果中的错误和异常",
  "使用 database_query 查询相似的已知 Bug"
]
</todo_list>
</good_example>

<good_example>
<request>搜索刘亦菲</request>
<todo_list>
[
  "使用 search 工具搜索'刘亦菲'相关信息"
]
</todo_list>
说明：搜索任务通常一次即可获取足够信息，无需重复调用
</good_example>

<good_example>
<request>查询登录相关的Bug</request>
<todo_list>
[
  "使用 database_query 工具查询Bug列表，query_type=bug_list，keywords=登录",
  "使用 grep 工具精准定位登录Bug所在计划，target=bug"
]
</todo_list>
说明：用户提到“Bug”，应查询bug_list且grep时设置target=bug
</good_example>

<good_example>
<request>修改这个Bug的优先级为高</request>
<todo_list>
[
  "使用 database_query 工具查找当前上下文中的Bug ID",
  "使用 modify 工具修改Bug的priority字段为'高'"
]
</todo_list>
说明：修改意图需要先定位目标，然后用modify工具生成预览
</good_example>

<good_example>
<request>创建一个登录失败的Bug</request>
<todo_list>
[
  "使用 create 工具创建Bug，标题=登录失败，优先级=高"
]
</todo_list>
说明：创建新Bug使用create工具，不需要预先查询
</good_example>

不好的 Todo 列表（避免这样）：
<bad_example>
<request>帮我测试登录功能</request>
<todo_list>
[
  "思考应该测试什么",
  "打开浏览器",
  "输入用户名",
  "输入密码",
  "点击登录",
  "等待页面加载",
  "检查是否成功",
  "分析结果",
  "生成报告",
  "保存到数据库"
]
</todo_list>
原因：太细碎，超过 5 项，没有按工具组织
</bad_example>
</examples>

<format>
必须返回以下格式（仅返回 XML 和 JSON，无其他文本）：
<todo_list>
[
  "第一项任务（具体且可执行）",
  "第二项任务（具体且可执行）",
  "第三项任务（具体且可执行）"
]
</todo_list>
</format>

现在请生成 Todo 列表：
"""
    
    @staticmethod
    def decide_prompt(todo: str, user_input: str, available_tools: list, context: dict) -> str:
        """
        ACT 阶段 Prompt - 决定是否执行并选择工具
        
        强约束：
        - 必须返回 XML 包装的 JSON 对象
        - 包含 execute / tool / params 三个关键字段
        - 提供详细的决策理由
        - 智能选择搜索引擎
        """
        tools_info = "\n".join([
            f"  <tool id=\"{t['name']}\" description=\"{t['description']}\"/>"
            for t in available_tools
        ])
        
        context_str = "\n".join([
            f"  - {k}: {str(v)[:100]}"
            for k, v in context.items()
        ]) if context else "无"
        
        return f"""你是一个任务执行决策专家。分析当前 Todo，决定是否执行以及使用哪个工具。

<system>
你的角色：根据 Todo 和当前上下文，做出执行决策
决策原则（严格按以下规则）：
1. 如果 Todo 包含工具操作词汇（search、搜索、查询、测试、browser、数据库等），必须执行（execute: true）
2. 如果 Todo 涉及外部信息获取或用户请求验证，必须执行（execute: true）
3. 仅当 Todo 是纯分析/整理且完全不涉及工具调用时，才考虑跳过（execute: false）
4. 优先执行而非跳过 - 当有疑问时，必须 execute: true
5. 提供清晰的决策理由
6. 工具参数应该具体且可执行

⭐ modify 工具参数提取规则（重要）：
- 使用 modify 工具时，必须从 current_context 中的 bug_list 提取 target_id
- 如果 bug_list 存在，取第一个 Bug 的 id 作为 target_id
- 例如：current_context 中有 "bug_list": [{{"id": 1, "title": "登录失败"}}]，则 target_id = 1
- 绝不能使用默认值或猜测 target_id，必须从 context 中获取

⭐ modify 工具状态值规则（重要）：
修改 status 字段时，必须使用以下合法的状态值（英文），不能使用中文：
- Bug 的合法状态值：new（新建）、assigned（已分配）、in_progress（进行中）、resolved（已解决）、closed（已关闭）、reopened（重新打开）
- BadCase 的合法状态值：new（新建）、pending（待处理）、resolved（已解决）、hold（搁置）、reopen（重新打开）、close（已关闭）
- 示例：用户说"关闭这个Bug"，应输出 "status": "closed"（Bug）或 "status": "close"（BadCase）
- 示例：用户说"标记为已解决"，应输出 "status": "resolved"

⭐ 搜索引擎智能选择规则（当使用 search 工具时）：
根据搜索关键词的语言、内容类型和用户意图智能选择最合适的搜索引擎：

【选择 "baidu"（百度）的情况】：
- 搜索关键词是中文（如："杨幂"、"C罗"、"Python教程"）
- 查询中国本土信息（如：中国企业、中国明星、国内新闻、中文网站）
- 涉及中国特色内容（如：淘宝、微信、支付宝、百度、腾讯、阿里巴巴）
- 查询中文资料、中文论坛、中文文档
- 混合中英文但以中文为主的查询

【选择 "google"（谷歌）的情况】：
- 搜索关键词是纯英文且涉及国际内容
- 查询国际技术资料（如：GitHub、Stack Overflow、官方英文文档）
- 搜索国际新闻、国际人物（如："Cristiano Ronaldo"、"Elon Musk"）
- 查询学术论文、英文教程
- 涉及国际平台和服务（如：AWS、Docker、Kubernetes）

【选择 "bing"（必应）的情况】：
- 用户明确要求使用必应
- 需要微软生态系统相关的搜索

⚠️ 重要原则：
- 中文关键词优先使用百度，即使包含英文技术词汇（如："Python 教程"、"React 入门"）
- 纯英文且明确国际化内容才使用 Google
- engine 参数值必须是小写："baidu" / "google" / "bing"（不是 "Baidu" / "Google" / "Bing"）
- 当不确定时，中文内容默认选择 "baidu"

示例：
- "杨幂" → engine: "baidu" （中文明星）
- "Cristiano Ronaldo" → engine: "google" （国际球星）
- "Python asyncio tutorial" → engine: "google" （英文技术文档）
- "Python 教程" → engine: "baidu" （中文教程，虽然包含 Python）
- "淘宝优惠券" → engine: "baidu" （中国本土电商）
- "github actions" → engine: "google" （国际技术平台）
</system>

<current_todo>
{todo}
</current_todo>

<user_request>
{user_input}
</user_request>

<available_tools>
{tools_info}
</available_tools>

<current_context>
{context_str}
</current_context>

<examples>
好的决策：
<good_example>
<todo>使用 browser_test 工具执行登录功能测试</todo>
<decision>
<execute>true</execute>
<tool>browser_test</tool>
<params>
{{
  "test_case": "登录功能",
  "steps": ["打开登录页", "输入用户名 admin", "输入密码 password", "点击登录按钮"]
}}
</params>
<reason>这是一个明确的测试任务，browser_test 工具正好用于此目的</reason>
</decision>
</good_example>

<good_example>
<todo>使用搜索工具查询 C罗 的信息</todo>
<decision>
<execute>true</execute>
<tool>search</tool>
<params>
{{
  "query": "C罗",
  "engine": "baidu",
  "limit": 10
}}
</params>
<reason>C罗是中文关键词，且用户可能需要中国地区的相关信息，选择百度搜索引擎</reason>
</decision>
</good_example>

<good_example>
<todo>使用 database_query 查询相似Bug</todo>
<decision>
<execute>true</execute>
<tool>database_query</tool>
<params>
{{
  "query_type": "find_similar",
  "keywords": "登录",
  "project_id": "1"
}}
</params>
<reason>查询数据库中与登录相关的Bug，使用find_similar类型和keywords参数</reason>
</decision>
</good_example>

<good_example>
<todo>使用 grep 工具精准定位登录Bug所在计划，target=bug</todo>
<decision>
<execute>true</execute>
<tool>grep</tool>
<params>
{{
  "keywords": "登录",
  "project_id": "1",
  "target": "bug"
}}
</params>
<reason>用户查询Bug，设置target=bug只分析Bug不分析BadCase</reason>
</decision>
</good_example>

<good_example>
<todo>使用 grep 工具定位登录相关缺陷</todo>
<decision>
<execute>true</execute>
<tool>grep</tool>
<params>
{{
  "keywords": "登录",
  "project_id": "1"
}}
</params>
<reason>使用grep工具模拟人类阅读习惯，精准定位BadCase/Bug的业务场景和归属计划</reason>
</decision>
</good_example>

<good_example>
<todo>使用 modify 工具修改Bug的priority字段为'高'</todo>
<decision>
<execute>true</execute>
<tool>modify</tool>
<params>
{{
  "target": "bug",
  "target_id": 1,
  "modifications": {{"priority": "高"}},
  "project_id": "1",
  "confirm": true
}}
</params>
<reason>修改Bug优先级，直接执行修改（confirm=true）</reason>
</decision>
</good_example>

<good_example>
<todo>使用 modify 工具修改Bug的status字段为'已解决'</todo>
<current_context>
  "bug_list": [
    {{"id": 1, "title": "登录失败", "status": "new", "plan_id": 31}},
    {{"id": 2, "title": "登录页面加载慢", "status": "new", "plan_id": 33}}
  ],
  "bugs_found": 2
</current_context>
<decision>
<execute>true</execute>
<tool>modify</tool>
<params>
{{
  "target": "bug",
  "target_id": 1,
  "modifications": {{"status": "resolved"}},
  "project_id": "1",
  "confirm": true
}}
</params>
<reason>从context的bug_list中获取第一个Bug的id=1作为target_id，修改其状态为resolved（已解决）</reason>
</decision>
</good_example>

<good_example>
<todo>使用 create 工具创建Bug，标题=登录失败，优先级=高</todo>
<decision>
<execute>true</execute>
<tool>create</tool>
<params>
{{
  "target": "bug",
  "fields": {{
    "title": "登录失败",
    "priority": "高",
    "description": "用户登录时出现失败"
  }},
  "project_id": "1",
  "confirm": true
}}
</params>
<reason>创建Bug，直接执行创建</reason>
</decision>
</good_example>

<good_example>
<todo>搜索 Python asyncio tutorial</todo>
<decision>
<execute>true</execute>
<tool>search</tool>
<params>
{{
  "query": "Python asyncio tutorial",
  "engine": "google",
  "limit": 10
}}
</params>
<reason>英文技术文档查询，Google 搜索引擎更适合查找国际技术资源</reason>
</decision>
</good_example>

不好的决策（避免）：
<bad_example>
<todo>思考应该测试什么</todo>
<decision>
<execute>true</execute>
<tool>unknown</tool>
<reason>太模糊了</reason>
</decision>
问题：Todo 太模糊，没有明确的工具对应
</bad_example>

<bad_example>
<todo>搜索信息</todo>
<decision>
<execute>true</execute>
<tool>search</tool>
<params>
{{
  "query": "信息"
}}
</params>
<reason>搜索信息</reason>
</decision>
问题：query 太模糊，没有指定 engine 参数（应根据关键词智能选择）
</bad_example>
</examples>

<format>
返回格式（仅 XML + JSON，无其他文本）：
<decision>
<execute>true/false</execute>
<tool>工具名（execute=true 时必填，选择最符合 Todo 的工具）</tool>
<params>
{{
  "param_name": "param_value",
  "engine": "baidu/google/bing (仅当工具是search时需要根据规则智能选择)"
}}
</params>
<reason>决策理由（简洁，1-2 句话，说明为什么选择该工具和参数）</reason>
</decision>

⚠️ 重要：
- 当 Todo 涉及搜索、查询、测试时，execute 必须是 true
- 不要因为担心错误而跳过任务，工具失败比跳过任务更好
- 使用 search 工具时，必须根据关键词特征智能选择合适的搜索引擎
</format>

现在请做出决策：
"""
    
    @staticmethod
    def observe_prompt(todo: str, action: dict, observation: dict, context: dict) -> str:
        """
        OBSERVE 阶段 Prompt - 分析工具结果并提取关键信息
        
        强约束：
        - 必须返回 XML 包装的结构化结果
        - 提取 key_findings / context_updates / next_step
        - 为下一个 Todo 准备上下文
        """
        observation_str = json.dumps(observation, ensure_ascii=False, indent=2)
        
        return f"""你是一个结果分析专家。分析工具执行结果，提取关键信息并更新上下文。

<system>
你的角色：分析工具结果，提取关键发现
分析原则：
1. 识别关键的 Bug、错误或成功指标
2. 更新执行上下文（供后续 Todo 使用）
3. 判断是否需要后续步骤
4. 提供清晰的结构化输出
5. 对于搜索工具：总结搜索结果的关键信息和结论，不要罗列原始搜索条目
</system>

<todo>
{todo}
</todo>

<action_taken>
工具：{action.get('tool')}
参数：{json.dumps(action.get('params', {}), ensure_ascii=False)}
</action_taken>

<tool_result>
{observation_str}
</tool_result>

<current_context>
{json.dumps(context, ensure_ascii=False, indent=2) if context else "{}"}
</current_context>

<examples>
好的分析：
<good_example>
<scenario>搜索工具返回10条关于"刘亦菲"的结果</scenario>
<result>
<key_findings>
  <finding type="info">搜索到刘亦菲相关信息，主要包含个人资料、作品和近期新闻</finding>
  <finding type="info">热门话题集中在影视作品和公众活动</finding>
</key_findings>
<context_update>
  "search_completed": true,
  "topic": "刘亦菲",
  "result_count": 10
</context_update>
<next_step>已完成搜索，可根据需要进一步分析</next_step>
</result>
</good_example>

<good_example>
<scenario>grep工具定位到登录相关的Bug</scenario>
<result>
<key_findings>
  <finding type="info">定位到2条登录相关的Bug</finding>
  <finding type="info">Bug ID: 1, 标题: 登录失败, 状态: new, 计划ID: 31</finding>
  <finding type="info">Bug ID: 2, 标题: 登录页面加载慢, 状态: new, 计划ID: 33</finding>
</key_findings>
<context_update>
  "bugs_found": 2,
  "bug_list": [
    {{"id": 1, "title": "登录失败", "status": "new", "plan_id": 31}},
    {{"id": 2, "title": "登录页面加载慢", "status": "new", "plan_id": 33}}
  ],
  "first_bug_id": 1
</context_update>
<next_step>可以使用modify工具修改Bug状态，target_id从bug_list中获取</next_step>
</result>
</good_example>

<good_example>
<scenario>测试工具返回登录错误</scenario>
<result>
<key_findings>
  <finding type="bug" severity="high">登录页面返回 500 错误</finding>
  <finding type="info">数据库连接超时，需要检查网络</finding>
</key_findings>
<context_update>
  "bugs_found": 1,
  "error_type": "database_timeout",
  "affected_component": "authentication_service"
</context_update>
<next_step>建议查询日志以定位根因</next_step>
</result>
</good_example>
</examples>

<format>
返回格式：
<result>
<key_findings>
  <finding type="bug/info/success">发现内容</finding>
  ...
</key_findings>
<context_update>
{{
  "key": "value"
}}
</context_update>
<next_step>建议的后续步骤</next_step>
</result>
</format>

现在请分析结果：
"""

def format_tools_for_prompt(tool_registry) -> list:
    """格式化工具信息"""
    return [
        {
            'name': tool.name,
            'description': tool.description
        }
        for tool in tool_registry.tools.values()
    ]


def extract_xml_field(text: Any, tag: str) -> str:
    """从 XML 中提取字段值，增加鲁棒性检查"""
    if not isinstance(text, str):
        return ''
    pattern = f'<{tag}>(.*?)</{tag}>'
    import re
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ''


def parse_xml_decision(text: Any) -> dict:
    """解析决策 XML 结果 - 兼容各种 JSON 响应和 Qwen 默认格式，增加搜索引擎智能选择"""
    result = {
        'execute': False,
        'tool': '',
        'params': {},
        'reason': ''
    }
    
    # 方案 -1: 如果是 list，取第一项
    if isinstance(text, list) and len(text) > 0:
        text = text[0]

    # 方案 0: 如果已经是 dict，直接处理
    if isinstance(text, dict):
        # 新增：智能推断工具参数（LLM 直接返回参数的情况）
        if 'engine' in text and 'query' in text:
            # 这是 search 工具的参数
            result['execute'] = True
            result['tool'] = 'search'
            result['params'] = text
            # 智能选择搜索引擎（如果没有指定）
            result['params'] = _smart_select_search_engine(result['params'])
            result['reason'] = '检测到搜索参数，自动执行 search 工具'
            return result
        
        if 'test_case' in text or 'steps' in text:
            # 这是 browser_test 工具的参数
            result['execute'] = True
            result['tool'] = 'browser_test'
            result['params'] = text
            result['reason'] = '检测到测试参数，自动执行 browser_test 工具'
            return result
        
        if 'sql' in text or 'query_type' in text:
            # 这是 database_query 工具的参数
            result['execute'] = True
            result['tool'] = 'database_query'
            result['params'] = text
            result['reason'] = '检测到数据库参数，自动执行 database_query 工具'
            return result
        
        if 'keywords' in text and 'project_id' in text and 'query_type' not in text:
            # 这是 grep 工具的参数（keywords + project_id，但没有query_type）
            result['execute'] = True
            result['tool'] = 'grep'
            result['params'] = text
            result['reason'] = '检测到grep参数，自动执行grep工具'
            return result
        
        if 'modifications' in text and 'target_id' in text:
            # 这是 modify 工具的参数
            result['execute'] = True
            result['tool'] = 'modify'
            result['params'] = text
            # 确保 confirm 默认为 True
            if 'confirm' not in result['params']:
                result['params']['confirm'] = True
            result['reason'] = '检测到修改参数，自动执行modify工具'
            return result
        
        if 'fields' in text and 'target' in text and text.get('target') in ['bug', 'badcase', 'plan', 'testcase']:
            # 这是 create 工具的参数
            result['execute'] = True
            result['tool'] = 'create'
            result['params'] = text
            # 确保 confirm 默认为 True
            if 'confirm' not in result['params']:
                result['params']['confirm'] = True
            result['reason'] = '检测到创建参数，自动执行create工具'
            return result
        
        # 兼容 Qwen 默认格式 (agent/action/script)
        if 'agent' in text or 'action' in text:
            result['execute'] = True
            
            # 智能映射 Qwen 的 Agent 名称到实际工具名
            qwen_agent = text.get('agent', '')
            qwen_action = text.get('action', '')
            qwen_script = str(text.get('script', '')).lower()
            
            # 默认映射
            actual_tool = qwen_agent or qwen_action
            
            # 规则匹配
            if qwen_agent == 'scriptAgent':
                if 'browser' in qwen_script:
                    actual_tool = 'browser_test'
                elif 'log' in qwen_script:
                    actual_tool = 'log_analyzer'
                elif 'accuracy' in qwen_script:
                    actual_tool = 'accuracy_tester'
                else:
                    actual_tool = 'browser_test'  # 兜底
            elif qwen_agent in ['bug_management_agent', 'mysql_agent']:
                actual_tool = 'database_query'
            
            # 浏览器操作工具映射
            tool_mapping = {
                'click': 'browser_click',
                'input': 'browser_input',
                'wait': 'browser_wait',
                'assert': 'browser_assert'
            }
            actual_tool = tool_mapping.get(actual_tool, actual_tool)
            
            result['tool'] = actual_tool
            result['params'] = text.get('info') or {}
            
            # 关键修复：将 top-level 的 action 合并到 params 中，作为 query_type 或 action
            qwen_action = text.get('action', '')
            if qwen_action and 'query_type' not in result['params'] and 'action' not in result['params']:
                result['params']['query_type'] = qwen_action
                result['params']['action'] = qwen_action
                
            # 如果 params 是空的，把 script 塞进去
            if not result['params'] and text.get('script'):
                result['params'] = {'script': text.get('script')}
            
            # 补充必要的默认参数
            if actual_tool == 'browser_test' and 'test_case' not in result['params']:
                result['params']['test_case'] = '自动测试'
            
            # 智能选择搜索引擎（如果是 search 工具）
            if actual_tool == 'search':
                result['params'] = _smart_select_search_engine(result['params'])
                
            result['reason'] = text.get('planActions') or 'LLM 自动分发任务'
            return result
            
        result['execute'] = text.get('execute', False) in [True, 'true', 'yes']
        result['tool'] = text.get('tool', '')
        result['params'] = text.get('params', {})
        result['reason'] = text.get('reason', '')
        
        # 智能选择搜索引擎（如果是 search 工具）
        if result['tool'] == 'search':
            result['params'] = _smart_select_search_engine(result['params'])
        
        return result

    # 方案 1: XML 格式
    decision_xml = extract_xml_field(text, 'decision')
    if decision_xml:
        # 提取 execute
        execute_str = extract_xml_field(decision_xml, 'execute')
        result['execute'] = execute_str.lower() in ['true', 'yes']
        
        # 提取 tool
        result['tool'] = extract_xml_field(decision_xml, 'tool')
        
        # 提取 reason
        result['reason'] = extract_xml_field(decision_xml, 'reason')
        
        # 提取 params（JSON 格式）
        params_str = extract_xml_field(decision_xml, 'params')
        try:
            result['params'] = json.loads(params_str) if params_str else {}
        except:
            result['params'] = {}
        
        # 智能选择搜索引擎（如果是 search 工具）
        if result['tool'] == 'search':
            result['params'] = _smart_select_search_engine(result['params'])
        
        if result['execute'] or result['tool']:
            return result
    
    # 方案 2: 字符串但包含 JSON 格式
    if isinstance(text, str):
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                # ✅ JSON 对象，提取相关字段
                result['execute'] = parsed.get('execute', False) in [True, 'true', 'yes']
                result['tool'] = parsed.get('tool', '')
                result['params'] = parsed.get('params', {})
                result['reason'] = parsed.get('reason', '')
                
                # 智能选择搜索引擎（如果是 search 工具）
                if result['tool'] == 'search':
                    result['params'] = _smart_select_search_engine(result['params'])
                
                return result
        except:
            pass
    
    # 方案 3: 默认
    result['execute'] = False
    return result


def _smart_select_search_engine(params: dict, llm=None) -> dict:
    """
    智能选择搜索引擎
    优先使用 LLM 智能推断，如果没有 LLM 则使用规则匹配
    
    规则（作为 LLM 失败后的退路）：
    - 中文关键词或中国本土信息 -> baidu
    - 英文关键词或国际信息 -> google
    - 混合或不确定 -> baidu (默认)
    - 中文优先级高于国际关键词
    """
    if not isinstance(params, dict):
        return params
    
    # 如果已经指定了 engine，直接返回
    if 'engine' in params and params['engine']:
        # 将 engine 转换为小写
        params['engine'] = params['engine'].lower()
        return params
    
    # 获取搜索关键词
    query = params.get('query') or params.get('keyword') or params.get('keywords') or params.get('search_query') or params.get('q') or ''
    
    if not query:
        # 没有 query，使用默认百度
        params['engine'] = 'baidu'
        return params
    
    # 如果有 LLM，使用 LLM 智能推断
    if llm:
        try:
            import asyncio
            # 如果是在异步上下文中，直接 await
            # 否则跳过 LLM 推断，使用规则
            if asyncio.get_event_loop().is_running():
                # 异步环境，但我们不能在同步函数中 await
                # 跳过 LLM，使用规则
                pass
            else:
                # 同步环境，也跳过
                pass
        except:
            pass
    
    # 使用基于规则的快速判断
    return _rule_based_engine_selection(params, query)


def _rule_based_engine_selection(params: dict, query: str) -> dict:
    """
    基于规则的搜索引擎选择
    作为 LLM 推断的退路方案
    """
    # 判断是否包含中文
    import re
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
    has_english = bool(re.search(r'[a-zA-Z]', query))
    
    # 中国本土关键词
    china_keywords = ['百度', '阿里', '腾讯', '淘宝', '京东', '微信', '支付宝', '中国', '国内', '中文']
    has_china_keyword = any(kw in query for kw in china_keywords)
    
    # 国际关键词
    international_keywords = ['github', 'stackoverflow', 'python', 'javascript', 'react', 'vue', 'docker', 'kubernetes', 'aws', 'google', 'facebook', 'twitter', 'tutorial', 'documentation', 'api']
    has_international_keyword = any(kw in query.lower() for kw in international_keywords)
    
    # 决策逻辑（中文优先级高）
    if has_china_keyword:
        # 有中国本土关键词，使用百度
        params['engine'] = 'baidu'
    elif has_chinese and not has_english:
        # 纯中文关键词，使用百度
        params['engine'] = 'baidu'
    elif has_chinese and has_english:
        # 混合中英文，中文优先，使用百度
        params['engine'] = 'baidu'
    elif has_international_keyword and not has_chinese:
        # 有国际关键词且没有中文，使用 Google
        params['engine'] = 'google'
    elif has_english and not has_chinese:
        # 纯英文关键词，使用 Google
        params['engine'] = 'google'
    else:
        # 其他情况，默认百度
        params['engine'] = 'baidu'
    
    return params


def parse_xml_findings(text: Any) -> dict:
    """解析发现 XML 结果 - 增加对对象格式的兼容"""
    result = {
        'findings': [],
        'context_update': {},
        'next_step': ''
    }
    
    # 方案 -1: 如果是 list
    if isinstance(text, list) and len(text) > 0:
        text = text[0]

    # 方案 0: 如果已经是 dict
    if isinstance(text, dict):
        # 兼容 Qwen 默认格式
        if 'planActions' in text or 'action' in text:
            result['findings'] = [text.get('planActions') or text.get('action')]
            result['context_update'] = text.get('info') or {}
            result['next_step'] = text.get('script') or ''
            return result
            
        result['findings'] = text.get('findings', [])
        result['context_update'] = text.get('context_update', {})
        result['next_step'] = text.get('next_step', '')
        return result

    # 方案 1: XML 格式
    findings_xml = extract_xml_field(text, 'key_findings')
    if findings_xml:
        import re
        findings = re.findall(r'<finding[^>]*>(.*?)</finding>', findings_xml)
        result['findings'] = findings
        
        # 提取 context_update
        context_str = extract_xml_field(text, 'context_update')
        try:
            result['context_update'] = json.loads(context_str) if context_str else {}
        except:
            result['context_update'] = {}
        
        # 提取 next_step
        result['next_step'] = extract_xml_field(text, 'next_step')
        return result
    
    # 方案 2: JSON 格式
    if isinstance(text, str):
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                result['findings'] = parsed.get('findings', [])
                result['context_update'] = parsed.get('context_update', {})
                result['next_step'] = parsed.get('next_step', '')
                return result
        except:
            pass
            
    return result


def parse_xml_todos(text: Any) -> list:
    """解析 Todo 列表 XML 结果 - 增加对列表对象的直接支持"""
    # 方案 0: 如果已经是 list
    if isinstance(text, list):
        todos = []
        for item in text:
            if isinstance(item, dict):
                todo_text = item.get('planActions') or item.get('action') or str(item)
                if todo_text and todo_text not in todos:
                    todos.append(todo_text)
            elif isinstance(item, str):
                todos.append(item)
        return todos if todos else ['分析用户请求并生成解决方案']

    # 方案 1: 正常 XML 格式
    todo_str = extract_xml_field(text, 'todo_list')
    if todo_str:
        try:
            return json.loads(todo_str) if todo_str else []
        except:
            pass
    
    # 方案 2: 字符串包含 JSON 格式
    if isinstance(text, str):
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, list):
                todos = []
                for item in parsed:
                    if isinstance(item, dict):
                        todo_text = item.get('planActions') or item.get('action') or str(item)
                        if todo_text and todo_text not in todos:
                            todos.append(todo_text)
                    elif isinstance(item, str):
                        todos.append(item)
                return todos if todos else ['分析用户请求并生成解决方案']
        except:
            pass
    
    # 方案 3: 默认
    return ['分析用户请求并生成解决方案']
