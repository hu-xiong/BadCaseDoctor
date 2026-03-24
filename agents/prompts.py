# -*- coding: utf-8 -*-
# agents/prompts.py
"""
ReAct Prompt 工程 - 公用强约束模板

提示词为公用：所有模型（GLM5、文心、Qwen、OpenAI 等）使用同一套 think/decide/observe 等模板，
仅底层调用的模型实例不同，不做按模型分支的差异化提示。

核心设计原则：
1. 长而精准 - 明确的系统上下文
2. XML 标签 - 固定输出格式
3. Good/Bad 示例 - 规范思考逻辑
4. Todo 锚定 - 保持任务焦点
"""

import json
import os
import re
from typing import Any, List, Dict, Union, Optional
try:
    import xml.etree.ElementTree as ET
except ImportError:
    ET = None


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
你的角色：分析用户请求，拆分成可执行的任务步骤。

【输出格式说明（必须遵守）】
你必须分两段输出（顺序固定）：
1) 先写「规划说明」：用 2～8 句中文说明你准备如何拆解任务，为什么这样拆。
   - 这一段禁止使用任何 XML 标签（包含 <todo_list>/<item>/<thinking>）。
2) 再输出机器可读规划：仅输出一个 <todo_list>...</todo_list> 块。

【项目名称转换规则】
- 如果上下文中提供了 project_name（项目名称），使用「在 XXX 项目中」而不是「在 project_id=1 中」
- 如果上下文中提供了 plan_name（计划名称），使用「在 XXX 计划下」而不是「在 plan_id=34 中」
- 示例：
  - ❌ 错误：「在 project_id=1 中搜索」→ ✅ 正确：「在 A 计划项目中搜索」
  - ❌ 错误：「plan_id=34 的记录」→ ✅ 正确：「在一个测试用例的计划下的记录」
  - ❌ 错误：「target_id=6 的 Bug」→ ✅ 正确：「创建测试用例这条记录」
- 如果上下文中**只有 project_id 而没有 project_name**，可以使用「当前项目」或直接省略项目描述，绝不能编造项目名称，也不要在文案里出现「project_id=1」等内部字段。

约束条件：
1. Todo 总数不超过 3 项（保持简洁）
2. 每项 Todo 必须对应一个可用工具
3. 使用明确的、可测量的语言

【核心规则 -技能优先的工具流程】：

1. **技能匹配优先**：
   -检查是否存在匹配的预定义技能
   - 如果匹配到技能（如 modify_bug、query_bug严格按照技能工作流执行
   -技能匹配阈值：0.3分以上

2. **标准流程兜底**：
   如果无匹配技能，按以下标准流程执行：

   **查询操作（单步流程）**：
   - 使用 grep工具搜索关键词
   - 查询意图关键词：查询、搜索、查看、找、列出、显示、单个关键字

   **修改操作（两步流程，缺一不可）**：
   - 第1步：使用 grep 工具搜索定位目标（必选）
   - 第2步：使用 modify 工具执行修改（必选）
   - 修改意图关键词：修改、改、更新、设为、改成、调整、期望结果、状态、优先级、负责人、标题
   - **不可修改的字段**：类型(type)、id、project_id、plan_id 等为系统固定字段，modify 无法修改；若用户要求修改这些字段，系统会单独提示并拒绝执行。
   - **重要**：
     - modify 工具支持的目标类型为 bug / badcase / testcase，不要因为早期文档误写而认为不支持 testcase。
     - 只要用户请求涉及「修改」Bug/BadCase/测试用例（改状态、期望结果、优先级、负责人、标题等），**通常**输出 2 条 Todo（先 grep 再 modify）；如确有必要增加额外校验/说明，总数也不得超过 3 条，且绝不能只输出 1 条（禁止跳过 grep）。
     - 当用户话语中明确出现「测试用例」「用例」等词时，应将目标类型视为 testcase，而不是随意改写为 Bug 或 BadCase。
     - 第二步 modify 会自动使用第一步 grep 定位到的 target_id，Todo 描述中只需写「将该测试用例/该Bug/该BadCase 的 XXX 修改为 YYY」，无需写 target_id。

   **创建操作（单步流程）**：
   - 使用 create 工具创建新的 Bug/BadCase/测试用例
   - 创建意图关键词：创建、新建、添加、增加
   - **复制/沿用某条测试用例新建**：在 fields 中传入 `copy_from_testcase_id`（或 `source_testcase_id`）为源用例 id，可与新 `title` 等同用；后端会将新用例的 `plan_id` 与源用例对齐（同一迭代计划）。

【grep 工具参数规范】：
- keywords: 搜索关键词（必填，如果要查询所有，设置为空字符串 "" 或 "*"）
- target: 分析目标 - bug/badcase/testcase/all（必填）
- project_id: 项目 ID（可选）
- **keywords 由你从用户话里识别**：
  - 用户若提到具体 BadCase/Bug/测试用例标题（如「雪碧和七喜」「创建测试用例」），必须把用户说的**完整标题原文**作为 keywords，不要将「和」等字替换成空格或省略，否则会查不到记录。
  - **区分字段名和标题**：用户若说的是字段名（如"前缀条件"、"前置条件"、"步骤"、"预期结果"、"期望结果"、"状态"等），**不要将字段名作为 keywords**，而应该从用户输入中提取**实际的标题**。例如：
    - 用户说「修改创建测试用例的前缀条件」→ 标题是「创建测试用例」→ keywords=创建测试用例
    - 用户说「修改登录 bug 的期望结果」→ 标题是「登录 bug」→ keywords=登录 bug
    - 用户说「修改雪碧和七喜的答案」→ 标题是「雪碧和七喜」→ keywords=雪碧和七喜

示例：使用 grep 工具搜索登录相关的 Bug，keywords=登录，target=bug
示例：用户说「修改雪碧和七喜的状态」→ 使用 grep 工具定位该 BadCase，keywords=雪碧和七喜，target=badcase
示例：用户说「修改创建测试用例的前缀条件」→ 使用 grep 工具定位该测试用例，keywords=创建测试用例，target=testcase
示例：使用 grep 工具查询所有 BadCase，keywords="" 或 keywords="*"，target=badcase
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
<request>界面</request>
<todo_list>
<item>使用 grep 工具搜索界面相关的Bug，keywords=界面，target=bug</item>
</todo_list>
说明：单关键字按查询意图处理，只需一步
</good_example>

<good_example>
<request>查询登录相关的Bug</request>
<todo_list>
<item>使用 grep 工具搜索登录相关的Bug，keywords=登录，target=bug</item>
</todo_list>
说明：查询操作只需一步
</good_example>

<good_example>
<request>修改登录Bug的状态为关闭</request>
<todo_list>
<item>使用 grep 工具搜索定位登录Bug，keywords=登录，target=bug</item>
<item>使用 modify 工具将Bug状态修改为closed</item>
</todo_list>
说明：修改操作必须两步：grep -> modify
</good_example>

<good_example>
<request>把高优先级的Bug都改成P1</request>
<todo_list>
<item>使用 grep 工具搜索高优先级Bug，keywords=高优先级，target=bug</item>
<item>使用 modify 工具批量修改优先级为P1</item>
</todo_list>
说明：批量修改也是两步流程
</good_example>

<good_example>
<request>把所有的BadCase都修改成已关闭状态</request>
<todo_list>
<item>使用 grep 工具查询所有BadCase，keywords=""，target=badcase</item>
<item>使用 modify 工具批量修改所有BadCase的状态为closed</item>
</todo_list>
说明：批量修改只需两个任务：grep 查询所有记录，然后一个 modify 任务批量修改。后端会自动处理所有记录。不要为每个记录生成单独的 modify 任务！
</good_example>

<good_example>
<request>所有Bug的状态都改成已解决</request>
<todo_list>
<item>使用 grep 工具查询所有Bug，keywords=""，target=bug</item>
<item>使用 modify 工具批量修改所有Bug的状态为resolved</item>
</todo_list>
说明：批量修改只需一个 modify 任务，后端会自动处理全部记录
</good_example>

<good_example>
<request>修改创建测试用例7的负责人为33</request>
<todo_list>
<item>使用 grep 工具搜索标题为「创建测试用例7」的测试用例，keywords=创建测试用例7，target=testcase</item>
<item>使用 modify 工具将该测试用例的负责人修改为33</item>
</todo_list>
说明：修改测试用例也必须两步，grep 时 target=testcase；modify 会使用上一步 grep 定位到的 target_id，无需在 Todo 中写 target_id。
</good_example>

<good_example>
<request>修改创建测试用例6的标题为创建测试用例8</request>
<todo_list>
<item>使用 grep 工具搜索标题为「创建测试用例6」的测试用例，keywords=创建测试用例6，target=testcase</item>
<item>使用 modify 工具将该测试用例的标题修改为创建测试用例8</item>
</todo_list>
说明：修改测试用例标题同样先 grep 再 modify，target=testcase。
</good_example>

<good_example>
<request>创建一个登录失败的Bug</request>
<todo_list>
<item>使用 create 工具创建Bug，标题=登录失败，优先级=高</item>
</todo_list>
说明：创建操作只需一步
</good_example>

<good_example>
<request>帮我测试登录功能</request>
<todo_list>
<item>使用 browser_test 工具执行登录功能测试</item>
</todo_list>
说明：browser_test 一次调用即可完成所有测试步骤
</good_example>

不好的 Todo 列表（避免这样）：
<bad_example>
<request>界面</request>
<todo_list>
<item>界面</item>
</todo_list>
原因：单关键字应生成 grep 查询步骤
</bad_example>

<bad_example>
<request>修改这个Bug的状态</request>
<todo_list>
<item>使用 modify 工具修改Bug状态</item>
</todo_list>
原因：修改操作必须先 grep 定位，再 modify
</bad_example>
</examples>

<format>
第二段必须是且仅包含：
- <todo_list>...</todo_list>（不要在该块外再输出 XML）
- 每一项任务用 <item>...</item> 包裹，多条即多个 <item>，格式稳定、易解析。
示例：
<todo_list>
<item>第一项任务（具体且可执行）</item>
<item>第二项任务（具体且可执行）</item>
<item>第三项任务（具体且可执行）</item>
</todo_list>
</format>

请先写「规划说明」，再输出 <todo_list>：

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
        - modify：params 可不全；引擎会按服务端补参逻辑在执行前合并（见 prompt 内「服务端补参」）
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
你必须分两段输出（顺序固定）：
1) **行动前说明**：用 3～12 句中文说明你接下来要怎么做、为什么这样做。可在首行使用「💭」（可选）。这一段**禁止使用 XML 标签**（包含 <decision>/<thinking> 等）。
2) **机器可读决策**：在说明之后，**单独**输出且仅输出一个 <decision>...</decision> 块。

你的角色：根据 Todo 和当前上下文，做出执行决策
决策原则（严格按以下规则）：
1. 强制绑定规则（优先级最高，绝不能违反）：
   - 如果 Todo 文本中明确包含「使用 grep 工具」或 \"use grep tool\"，则 tool 字段必须为 \"grep\"。
   - 如果 Todo 文本中明确包含「使用 modify 工具」或 \"use modify tool\"，则 tool 字段必须为 \"modify\"。
   - 如果 Todo 文本中明确包含「使用 create 工具」或 \"use create tool\"，则 tool 字段必须为 \"create\"。
   - 如果 Todo 文本中明确包含「使用 browser_test 工具」或 \"use browser_test tool\"，则 tool 字段必须为 \"browser_test\"。
   - 当存在上述绑定时，绝对禁止选择其他工具（例如：Todo 里写了「使用 modify 工具」，决策结果却给出 browser_test，这是错误的）。
2. 在没有明确「使用 XXX 工具」字样时，再根据 Todo 内容选择最合适的工具。
3. 如果 Todo 包含工具操作词汇（search、搜索、查询、测试、browser、数据库等），必须执行（execute: true）
4. 如果 Todo 涉及外部信息获取或用户请求验证，必须执行（execute: true）
5. 仅当 Todo 是纯分析/整理且完全不涉及工具调用时，才考虑跳过（execute: false）
6. 优先执行而非跳过 - 当有疑问时，必须 execute: true
7. 提供清晰的决策理由
8. 工具参数应该具体且可执行
9. create 工具：**params 中 confirm 必须为 false**（仅生成预览与 diff）；禁止在对话首轮直接落库，采纳由用户在左侧列表完成。

⭐ 人类式先检索再阅读（modify 前必读）：
- 流程：先 grep 检索出候选列表（badcase_list/bug_list/testcase_location），对候选做 rerank，**分高的**作为 target_id；支持 BadCase、Bug、测试用例( testcase )。
- 若 context 中尚无列表，必须先 grep：grep(keywords="用户话里的标题或关键词", target="badcase"或"bug"或"testcase"或"all", project_id=当前项目)。可选 plan_id 限定当前迭代。grep 支持关键词拆分模糊匹配。
- 选 target_id 时：系统会对候选按与关键词的匹配度 rerank，分高的即可；修改目标类型由 target 指定（bug/badcase/testcase）。
- 字段命名统一（避免混淆）：**答案用 answer**，**正确答案用 correct_answer**（由 modify 工具映射到数据库字段）。
- 不要在 params 里编造数字 id；若 context 中已有上一步 grep 结果，你可写出 target_id；**若不确定，params 可只含 target / 或留空，真实执行以服务端补参为准**（见下条）。

⭐ 服务端补参（真实可靠性口径，优先遵守）：
- 你只要 **execute=true 且 tool=modify** 即可完成任务绑定；**target_id、modifications 若写不全，不必硬编**，引擎会在调用 modify 工具前自动补全：合并上一步 grep 的候选 id、必要时自动再 grep、结合用户原话与探索记录生成 modifications。
- 你能写出完整 params（含 target、target_id、modifications）时，日志更清晰，但最终仍以 **服务端合并、校验后的参数** 为准。

⭐ modify 工具状态值规则（重要）：
修改 status 字段时，必须使用以下合法的状态值（英文），不能使用中文：
- Bug 的合法状态值：new（新建）、assigned（已分配）、in_progress（进行中）、resolved（已解决）、closed（已关闭）、reopened（重新打开）
- BadCase 的合法状态值：new（新建）、pending（待处理）、resolved（已解决）、hold（搁置）、reopened（重新打开）、closed（已关闭）
- 示例：用户说"关闭这个Bug"，应输出 "status": "closed"（Bug或BadCase都用closed）
- 示例：用户说"标记为已解决"，应输出 "status": "resolved"
- 示例：用户说"重新打开"，应输出 "status": "reopened"

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
  "confirm": false
}}
</params>
<reason>修改Bug优先级，先沙箱预览（confirm=false），用户确认后再执行</reason>
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
  "confirm": false
}}
</params>
<reason>从context的bug_list中获取第一个Bug的id=1作为target_id，修改其状态为resolved，先沙箱预览</reason>
</decision>
</good_example>

<good_example>
<todo>使用 modify 工具修改BadCase的status字段为'已关闭'</todo>
<current_context>
  "badcase_list": [
    {{"id": 3, "title": "测试badcase", "status": "closed", "plan_id": 1}},
    {{"id": 5, "title": "雪碧和七喜", "status": "pending", "plan_id": 2}}
  ]
</current_context>
<decision>
<execute>true</execute>
<tool>modify</tool>
<params>
{{
  "target": "badcase",
  "target_id": 3,
  "modifications": {{"status": "closed"}},
  "project_id": "1",
  "confirm": false
}}
</params>
<reason>从context的badcase_list中获取第一个BadCase的id=3作为target_id，修改其状态为closed（注意BadCase和Bug都用closed而不是close）</reason>
</decision>
</good_example>

<good_example>
<todo>修改雪碧和七喜的正确答案为理解正确</todo>
<current_context>
  "badcase_list": [{{"id": 5, "title": "雪碧和七喜", "status": "resolved"}}]
</current_context>
<decision>
<execute>true</execute>
<tool>modify</tool>
<params>
{{
  "target": "badcase",
  "target_id": 5,
  "modifications": {{"correct_answer": "理解正确"}},
  "project_id": "1",
  "confirm": false
}}
</params>
<reason>从context的badcase_list中取标题为「雪碧和七喜」的id=5；字段命名统一：正确答案用correct_answer，值为理解正确</reason>
</decision>
</good_example>

<good_example>
<todo>修改雪碧和七喜的答案为2</todo>
<current_context>
  "badcase_list": [{{"id": 5, "title": "雪碧和七喜", "status": "resolved"}}]
</current_context>
<decision>
<execute>true</execute>
<tool>modify</tool>
<params>
{{
  "target": "badcase",
  "target_id": 5,
  "modifications": {{"answer": "2"}},
  "project_id": "1",
  "confirm": false
}}
</params>
<reason>字段命名统一：答案用answer（会映射到数据库的correct_answer）</reason>
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
  "confirm": false
}}
</params>
<reason>创建 Bug：先沙箱预览（confirm=false），用户在列表中采纳后再落库</reason>
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
第二段必须是且仅包含：
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

请先写「行动前说明」，再输出 <decision>：

现在请做出决策：
"""

    @staticmethod
    def decide_prompt_react_dynamic(
        user_input: str,
        available_tools: list,
        context: dict,
        *,
        round_idx: int,
        last_observation: Optional[dict],
        last_analysis: Optional[dict],
        plan_hints: List[str],
    ) -> str:
        """
        动态 ReAct：每一步根据「当前上下文 + 上一步观察」再决策。
        输出：先自然语言说明（Agent 行动前推理，非模型深度思考），再输出 <decision>...</decision>。
        """
        tools_info = "\n".join([
            f"  <tool id=\"{t['name']}\" description=\"{t['description']}\"/>"
            for t in available_tools
        ])
        context_str = "\n".join([
            f"  - {k}: {str(v)[:500]}"
            for k, v in (context or {}).items()
        ]) if context else "无"
        obs_s = ""
        if last_observation is not None:
            try:
                raw = json.dumps(last_observation, ensure_ascii=False, indent=2)
                obs_s = raw[:12000] + ("…" if len(raw) > 12000 else "")
            except Exception:
                obs_s = str(last_observation)[:8000]
        else:
            obs_s = "（尚无：这是本轮第一次行动前决策。）"
        ana_s = ""
        if last_analysis is not None:
            try:
                ana_s = json.dumps(last_analysis, ensure_ascii=False, indent=2)[:6000]
            except Exception:
                ana_s = str(last_analysis)[:4000]
        hints = ""
        if plan_hints:
            hints = "\n".join(f"  {i + 1}. {h}" for i, h in enumerate(plan_hints[:20]))

        return f"""你是任务执行 Agent。当前是第 {round_idx + 1} 轮「思考 → 行动 → 观察」循环。

<system>
你必须分两段输出（顺序固定）：
1) **行动前说明**：用 3～12 句中文，说明「下一步要做什么、为什么、如何执行」，像对同事说明计划一样。
   - 可在首行使用「💭」作为提示（可选），便于界面展示「思考」。
   - 这是 Agent 的推理与沟通，**不要**使用任何 XML 标签（含 <thinking>），也不要模仿「模型内部思维链」格式。
2) **机器可读决策**：在说明之后，**单独**输出且仅输出一个 <decision>...</decision> 块，结构必须与下面 <format> 一致，以便系统解析工具调用。
决策规则与原有 decide 一致：grep 先于 modify、params 可部分省略由服务端补全、create/modify 的 confirm=false 等。
若用户目标已达成、无需再调工具，则 <execute>false</execute> 并在 <reason> 中说明「任务已完成」或原因。
</system>

<user_request>
{user_input}
</user_request>

<round_index>{round_idx}</round_index>

<initial_plan_hints>
（仅作背景参考，**非强制步骤顺序**；实际每轮须结合最新观察自主决定。）
{hints or "（无单独规划列表）"}
</initial_plan_hints>

<current_context>
{context_str}
</current_context>

<last_observation>
{obs_s}
</last_observation>

<last_analysis>
{ana_s if ana_s else "（无）"}
</last_analysis>

<available_tools>
{tools_info}
</available_tools>

<format>
第二段必须是且仅包含：
<decision>
<execute>true 或 false</execute>
<tool>工具名</tool>
<params>{{ ... JSON ... }}</params>
<reason>简短理由</reason>
</decision>
</format>

请先写「行动前说明」，再写 <decision> 块：
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
你必须分两段输出（顺序固定）：
1) **分析说明**：用若干句中文，说明你从工具结果里看到了什么、对后续步骤的含义；可在首行使用「💭」（可选）。**不要使用 XML 标签**，不要输出 <result> 或 <finding> 等标签。
2) **机器可读结果**：在说明之后，**单独**输出且仅输出一个 <result>...</result> 块，结构必须与下方 <format> 一致，以便系统解析。

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
第二段必须是且仅包含：
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

请先写「分析说明」，再写 <result> 块：

现在请分析结果：
"""

    @staticmethod
    def ui_params_summary_prompt(
        todo: str,
        tool: str,
        params: Optional[dict],
        reason: str = "",
        todos_overview: str = "",
    ) -> str:
        """面向聊天面板：把结构化入参改写成用户可读说明（不展示原始 JSON）。"""
        pj = json.dumps(params or {}, ensure_ascii=False, indent=2)
        r = (reason or "").strip()
        rline = f"\n模型简述：{r[:900]}" if r else ""
        tv = (todos_overview or "").strip() or "（仅本步，未提供完整列表）"
        return f"""你是 ReAct 助手。请先**对照下方完整待办列表**，确认本步在整体任务中的位置，再用 2～8 句中文说明本步**即将执行什么**（工具调用要点：工具名、检索词、目标类型、关键 id）。不要用 JSON/XML/代码块。

【待办步骤全貌（必须先阅读）】
{tv}

【本步对应的 Todo 条目】
{todo}

工具：{tool}
结构化参数（仅供理解，勿原文复述）：
{pj}{rline}
"""

    @staticmethod
    def ui_decision_summary_prompt(todo: str, decision: dict, todos_overview: str = "") -> str:
        """面向聊天面板：总结决策结论（替代原始 XML）。"""
        tool = str(decision.get("tool") or "")
        ex = "是" if decision.get("execute") else "否"
        pj = json.dumps(decision.get("params") or {}, ensure_ascii=False, indent=2)
        r = (decision.get("reason") or "").strip()
        rline = f"\n模型决策理由：{r[:1200]}" if r else ""
        tv = (todos_overview or "").strip() or "（仅本步，未提供完整列表）"
        return f"""请对照【待办步骤全貌】，用 2～8 句中文写清**本步要完成什么**（是否执行、用哪个工具、关键意图）。不要输出 XML/JSON/代码块。

【待办步骤全貌】
{tv}

【本步 Todo】
{todo}

是否执行：{ex}
工具：{tool}
参数摘要（仅供理解）：
{pj}{rline}
"""

    @staticmethod
    def ui_observe_summary_prompt(
        todo: str, tool: str, observation: Any, todos_overview: str = ""
    ) -> str:
        """面向聊天面板：总结工具执行结果（替代原始 observe XML）。"""
        try:
            if isinstance(observation, dict):
                obs_s = json.dumps(observation, ensure_ascii=False)
            else:
                obs_s = str(observation)
        except Exception:
            obs_s = str(observation)
        max_len = 8000
        if len(obs_s) > max_len:
            obs_s = obs_s[:max_len] + "\n…（已截断）"
        tv = (todos_overview or "").strip() or "（仅本步，未提供完整列表）"
        return f"""请对照【待办步骤全貌】，用 2～10 句中文总结**本步执行得怎么样**：成败、关键数据、是否达成该 Todo 的预期、对后续步骤的含义。不要输出 XML/JSON/代码块。

【待办步骤全貌】
{tv}

【本步 Todo】
{todo}
工具：{tool}

工具返回（节选）：
{obs_s}
"""


def format_tools_for_prompt(tool_registry) -> list:
    """格式化工具信息。REACT_TOOL_DESC_MAX_CHARS>0 时截断描述，缩短首轮 THINK prompt（不改模型，仅减 token）。"""
    try:
        max_chars = int(os.getenv("REACT_TOOL_DESC_MAX_CHARS", "0") or "0")
    except Exception:
        max_chars = 0
    out = []
    for tool in tool_registry.tools.values():
        desc = tool.description or ""
        if max_chars > 0 and len(desc) > max_chars:
            desc = desc[:max_chars].rstrip() + "…"
        out.append({"name": tool.name, "description": desc})
    return out


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
        
        # grep 工具参数识别（放宽条件：有 target 和 project_id 也识别为 grep）
        if 'target' in text and 'project_id' in text and 'query_type' not in text and 'modifications' not in text and 'fields' not in text:
            result['execute'] = True
            result['tool'] = 'grep'
            result['params'] = text
            result['reason'] = '检测到grep参数（target+project_id），自动执行grep工具'
            return result
        
        if 'modifications' in text and ('target_id' in text or 'target' in text):
            # 这是 modify 工具的参数
            result['execute'] = True
            result['tool'] = 'modify'
            result['params'] = text
            # 确保 confirm 默认为 False（沙箱预览模式），需要用户确认后才执行
            if 'confirm' not in result['params']:
                result['params']['confirm'] = False
            result['reason'] = '检测到修改参数，自动执行modify工具（沙箱预览模式）'
            return result
        
        if 'fields' in text and 'target' in text and text.get('target') in ['bug', 'badcase', 'plan', 'testcase']:
            # 这是 create 工具的参数
            result['execute'] = True
            result['tool'] = 'create'
            result['params'] = text
            # 与 modify 一致：对话中 create 一律沙箱预览，禁止直接落库
            result['params']['confirm'] = False
            result['reason'] = '检测到创建参数，自动执行 create 工具（沙箱预览模式）'
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

    # 方案 1: <todo_list> 内按 XML 解析（<item>/<todo>/<step>），不再优先 json.loads
    todo_str = extract_xml_field(text, 'todo_list')
    if todo_str and todo_str.strip():
        s = todo_str.strip()
        # 先按 XML 解析
        if ET is not None:
            try:
                root = ET.fromstring(f"<root>{s}</root>")
                items = []
                for node in root.iter():
                    tag = (node.tag or "").lower()
                    if tag in ("todo", "item", "step"):
                        content = (node.text or "").strip()
                        if content:
                            items.append(content)
                if items:
                    return items
            except Exception:
                pass
        # 无标签时按行兜底
        lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
        if lines:
            cleaned = [re.sub(r'^[-*•\d\.\)]+\s*', '', ln).strip() for ln in lines if re.sub(r'^[-*•\d\.\)]+\s*', '', ln).strip()]
            if cleaned:
                return cleaned
        # 兼容旧版：内容恰为 JSON 数组字符串时再试
        try:
            out = json.loads(s)
            if isinstance(out, list) and out:
                return [str(x).strip() for x in out if str(x).strip()]
        except Exception:
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
