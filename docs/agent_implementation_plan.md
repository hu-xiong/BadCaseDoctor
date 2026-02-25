# BadCase Doctor Agent 功能实现方案

## 1. 概述

基于 Browser-use 工具，实现自动化测试、BadCase 定位和对话准确率评估的 Agent 系统。

## 2. 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                   前端界面层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 测试用例管理  │  │ Bug审核中心   │  │ BadCase定位  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                   API 路由层                              │
│  /api/agent/browser-use/test                             │
│  /api/agent/browser-use/badcase                          │
│  /api/agent/browser-use/conversation                     │
│  /api/bugs/review/*                                      │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                   Agent 处理层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │BrowserUseAgent│  │BugReviewAgent │  │ MySQL/Redis  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                   工具集成层                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Browser-use  │  │  Prometheus  │  │  LLM (Qwen)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 3. 核心功能模块

### 3.1 测试用例自动执行

**功能描述:**
- 根据测试用例定义，使用 Browser-use 模拟人工测试
- 自动生成 Bug 列表
- 支持人工审核(接受/拒绝/修改)

**实现步骤:**

#### 步骤 1: 测试用例数据模型

```python
# models/test_case.py
class TestCase:
    id: str
    name: str
    description: str
    url: str  # 测试页面URL
    steps: List[Dict]  # 测试步骤
    expected_result: str  # 预期结果
    priority: str  # 优先级
    
# 示例测试步骤
{
    "action": "click",
    "selector": "#login-button",
    "description": "点击登录按钮"
}
```

#### 步骤 2: Browser-use 集成

```python
# agents/browser_use_agent.py (已创建)

# 安装依赖
pip install browser-use playwright

# 初始化浏览器
from browser_use import BrowserUse

browser = BrowserUse(
    headless=False,
    timeout=30000,
    viewport={"width": 1920, "height": 1080}
)

# 执行测试步骤
await browser.goto(test_case.url)
for step in test_case.steps:
    await browser.execute_step(step)
    
# 截图
await browser.screenshot("test_result.png")
```

#### 步骤 3: Bug 生成与审核

```python
# Bug 数据结构
{
    "id": "pending_001",
    "title": "登录按钮无响应",
    "severity": "high",
    "status": "pending_review",  # 待审核
    "description": "...",
    "steps_to_reproduce": [...],
    "screenshots": [...],
    "test_case_id": "TC_001",
    "created_at": "2026-01-22T13:30:00"
}

# 审核流程
1. 用户查看待审核 Bug 列表
2. 点击 Bug 查看详细信息
3. 选择操作:
   - ✅ 接受: Bug 转为正式 Bug 记录
   - ❌ 拒绝: 标记为误报
   - ✏️ 修改: 调整 Bug 信息后接受
```

### 3.2 BadCase 自动化定位

**功能描述:**
- 模拟对话，复现 BadCase
- 采集 Prometheus 性能指标
- 使用 LLM 分析问题原因
- 生成修复建议

**实现步骤:**

#### 步骤 1: BadCase 复现

```python
# 1. 获取 BadCase 详情
badcase = {
    "id": 1,
    "title": "对话响应超时",
    "reproduction_steps": [
        "输入长文本问题",
        "等待系统响应",
        "观察响应时间"
    ],
    "expected": "2秒内响应",
    "actual": "超过10秒无响应"
}

# 2. Browser-use 模拟对话
browser = BrowserUse()
await browser.goto("http://localhost:5173/chat")

for step in badcase["reproduction_steps"]:
    if "输入" in step:
        await browser.type("#chat-input", "长文本内容...")
        await browser.click("#send-button")
    elif "等待" in step:
        start_time = time.time()
        await browser.wait_for_selector(".message-response")
        response_time = time.time() - start_time
```

#### 步骤 2: Prometheus 指标采集

```python
# 安装依赖
pip install prometheus-client requests

# 查询指标
from prometheus_api_client import PrometheusConnect

prom = PrometheusConnect(url="http://prometheus:9090")

# 查询响应时间
response_time_query = 'http_request_duration_seconds{path="/api/chat"}'
response_times = prom.custom_query(response_time_query)

# 查询错误率
error_rate_query = 'rate(http_requests_total{status=~"5.*"}[5m])'
error_rates = prom.custom_query(error_rate_query)

# 查询资源使用
cpu_query = 'process_cpu_seconds_total'
memory_query = 'process_resident_memory_bytes'
```

#### 步骤 3: LLM 问题分析

```python
# 使用 LLM 分析问题
analysis_prompt = f"""
根据以下信息分析 BadCase 的根本原因:

BadCase 信息:
{badcase}

性能指标:
- 响应时间: {response_time}ms
- 错误率: {error_rate}
- CPU 使用率: {cpu_usage}%
- 内存使用: {memory_usage}MB

对话日志:
{conversation_logs}

请分析:
1. 问题的根本原因
2. 具体的修复建议
3. 优化方案
"""

result = llm.invoke(analysis_prompt)
```

### 3.3 对话准确率测试

**功能描述:**
- 使用测试集批量测试对话质量
- 支持 Browser-use 模拟或 API 调用
- 自动评估回答准确性
- 生成测试报告

**实现步骤:**

#### 步骤 1: 测试集数据结构

```python
# 测试集格式
test_set = [
    {
        "id": 1,
        "question": "如何使用系统?",
        "expected_answer": "系统使用步骤包括...",
        "category": "功能使用",
        "difficulty": "easy"
    },
    {
        "id": 2,
        "question": "如何解决登录问题?",
        "expected_answer": "登录问题的解决方法...",
        "category": "问题排查",
        "difficulty": "medium"
    }
    # ... 更多测试用例
]
```

#### 步骤 2: 对话测试执行

```python
# 方式1: Browser-use 模拟
async def test_with_browser(test_set):
    browser = BrowserUse()
    await browser.goto("http://localhost:5173/chat")
    
    results = []
    for item in test_set:
        # 发送问题
        await browser.type("#chat-input", item["question"])
        await browser.click("#send-button")
        
        # 等待响应
        await browser.wait_for_selector(".message-response")
        actual_answer = await browser.text(".message-response")
        
        # 记录结果
        results.append({
            "question": item["question"],
            "expected": item["expected_answer"],
            "actual": actual_answer,
            "timestamp": datetime.now()
        })
    
    return results

# 方式2: API 调用
async def test_with_api(test_set):
    import aiohttp
    
    results = []
    async with aiohttp.ClientSession() as session:
        for item in test_set:
            start_time = time.time()
            
            async with session.post(
                "http://localhost:5000/api/chat",
                json={"message": item["question"]}
            ) as resp:
                response = await resp.json()
                response_time = time.time() - start_time
                
                results.append({
                    "question": item["question"],
                    "expected": item["expected_answer"],
                    "actual": response.get("answer"),
                    "response_time": response_time
                })
    
    return results
```

#### 步骤 3: 答案质量评估

```python
# 使用 LLM 评估答案质量
def evaluate_answer(question, expected, actual):
    prompt = f"""
    评估以下回答的质量:
    
    问题: {question}
    标准答案: {expected}
    实际回答: {actual}
    
    请给出:
    1. 相似度评分 (0-1)
    2. 准确性评分 (0-1)
    3. 是否正确 (True/False)
    4. 评价理由
    
    以 JSON 格式返回。
    """
    
    result = llm.invoke(prompt)
    return json.loads(result)

# 生成测试报告
def generate_report(results):
    total = len(results)
    correct = sum(1 for r in results if r["is_correct"])
    accuracy = correct / total if total > 0 else 0
    avg_similarity = sum(r["similarity_score"] for r in results) / total
    
    report = {
        "total_questions": total,
        "correct_answers": correct,
        "accuracy": accuracy,
        "avg_similarity": avg_similarity,
        "avg_response_time": sum(r["response_time"] for r in results) / total,
        "details": results
    }
    
    return report
```

## 4. API 接口设计

### 4.1 测试用例执行

```python
# POST /api/agent/browser-use/test
Request:
{
    "test_case_id": "TC_001",
    "url": "http://localhost:5173/login",
    "steps": [
        {"action": "type", "selector": "#username", "value": "test"},
        {"action": "type", "selector": "#password", "value": "123456"},
        {"action": "click", "selector": "#login-btn"}
    ],
    "expected_result": "登录成功"
}

Response:
{
    "code": 200,
    "data": {
        "execution_id": "exec_001",
        "bugs_found": [
            {
                "id": "pending_001",
                "title": "登录按钮无响应",
                "status": "pending_review"
            }
        ]
    }
}
```

### 4.2 Bug 审核

```python
# GET /api/bugs/review/pending
Response:
{
    "code": 200,
    "data": {
        "pending_bugs": [...],
        "total": 5
    }
}

# POST /api/bugs/review/approve
Request:
{
    "bug_id": "pending_001",
    "comment": "确认为有效 Bug"
}

# POST /api/bugs/review/reject
Request:
{
    "bug_id": "pending_001",
    "comment": "非 Bug，操作正常"
}
```

### 4.3 BadCase 定位

```python
# POST /api/agent/browser-use/badcase
Request:
{
    "badcase_id": 1,
    "reproduction_steps": [...],
    "metric_queries": [
        "http_request_duration_seconds",
        "error_rate"
    ]
}

Response:
{
    "code": 200,
    "data": {
        "reproduced": true,
        "metrics": {...},
        "root_cause": "模型推理超时",
        "fix_suggestions": [...]
    }
}
```

### 4.4 对话测试

```python
# POST /api/agent/browser-use/conversation
Request:
{
    "test_set_id": "TS_001",
    "method": "browser",  # or "api"
    "test_cases": [...]
}

Response:
{
    "code": 200,
    "data": {
        "test_id": "test_001",
        "accuracy": 0.85,
        "report_url": "/api/conversation/test/report/test_001"
    }
}
```

## 5. 数据库设计

### 5.1 测试用例表

```sql
CREATE TABLE test_case (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    project_id INT,
    url VARCHAR(500),
    steps JSON,
    expected_result TEXT,
    priority VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES project(id)
);
```

### 5.2 Bug 表 (扩展)

```sql
-- 在现有 bug 表基础上增加字段
ALTER TABLE bug ADD COLUMN source VARCHAR(50) DEFAULT 'manual';  -- manual / automated_test
ALTER TABLE bug ADD COLUMN test_case_id INT;
ALTER TABLE bug ADD COLUMN review_status VARCHAR(20) DEFAULT 'approved';  -- pending_review / approved / rejected
ALTER TABLE bug ADD COLUMN reviewed_by INT;
ALTER TABLE bug ADD COLUMN reviewed_at TIMESTAMP;
ALTER TABLE bug ADD COLUMN review_comment TEXT;
```

### 5.3 对话测试记录表

```sql
CREATE TABLE conversation_test (
    id INT PRIMARY KEY AUTO_INCREMENT,
    test_set_id VARCHAR(100),
    project_id INT,
    total_questions INT,
    correct_answers INT,
    accuracy DECIMAL(5,4),
    avg_similarity DECIMAL(5,4),
    avg_response_time INT,  -- ms
    test_results JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES project(id)
);
```

## 6. 部署与配置

### 6.1 依赖安装

```bash
# Python 依赖
pip install browser-use
pip install playwright
pip install prometheus-client
pip install prometheus-api-client

# 初始化 Playwright
playwright install chromium

# Prometheus 配置 (docker-compose.yml)
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

### 6.2 环境变量配置

```python
# config.py
class Config:
    # Browser-use 配置
    BROWSER_HEADLESS = os.getenv('BROWSER_HEADLESS', 'false') == 'true'
    BROWSER_TIMEOUT = int(os.getenv('BROWSER_TIMEOUT', '30000'))
    
    # Prometheus 配置
    PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 'http://localhost:9090')
    
    # 测试配置
    TEST_CASE_TIMEOUT = int(os.getenv('TEST_CASE_TIMEOUT', '60'))
    BUG_AUTO_APPROVE = os.getenv('BUG_AUTO_APPROVE', 'false') == 'true'
```

## 7. 使用流程

### 7.1 测试用例执行流程

1. **创建测试用例**
   - 在前端创建或导入测试用例
   - 定义测试步骤和预期结果

2. **执行测试**
   - 点击"执行测试"按钮
   - Browser-use 自动模拟操作
   - 系统生成 Bug 列表

3. **审核 Bug**
   - 打开 Bug 审核中心
   - 查看待审核 Bug 详情
   - 选择接受/拒绝/修改

4. **处理已接受的 Bug**
   - 已接受的 Bug 进入正式 Bug 跟踪流程
   - 分配给开发人员修复

### 7.2 BadCase 定位流程

1. **选择 BadCase**
   - 从 BadCase 列表选择需要定位的问题

2. **执行复现**
   - 系统自动模拟复现步骤
   - 采集性能指标

3. **查看分析结果**
   - LLM 自动分析根本原因
   - 提供修复建议

4. **修复验证**
   - 开发人员根据建议修复
   - 重新执行验证

### 7.3 对话测试流程

1. **准备测试集**
   - 导入或创建测试集
   - 包含问题-答案对

2. **执行测试**
   - 选择测试方法(Browser/API)
   - 批量执行测试

3. **查看报告**
   - 查看准确率统计
   - 分析错误案例

4. **优化改进**
   - 根据测试结果优化系统
   - 重新测试验证

## 8. 下一步开发计划

### Phase 1: 基础集成 (1-2周)
- [ ] 安装和配置 Browser-use
- [ ] 实现基础测试用例执行
- [ ] 创建 Bug 审核界面
- [ ] 实现审核流程 API

### Phase 2: BadCase 定位 (1-2周)
- [ ] 集成 Prometheus 指标采集
- [ ] 实现 BadCase 复现逻辑
- [ ] 集成 LLM 分析
- [ ] 创建定位结果展示界面

### Phase 3: 对话测试 (1周)
- [ ] 实现对话测试执行
- [ ] 创建测试集管理功能
- [ ] 实现答案质量评估
- [ ] 生成测试报告

### Phase 4: 优化与完善 (1周)
- [ ] 性能优化
- [ ] 错误处理完善
- [ ] 文档编写
- [ ] 集成测试

## 9. 注意事项

1. **安全性**
   - Bug 审核需要权限控制
   - 测试执行需要隔离环境
   - API 调用需要认证

2. **性能**
   - Browser-use 操作较慢,需要合理设置超时
   - 批量测试需要并发控制
   - Prometheus 查询需要优化

3. **可靠性**
   - Browser-use 可能失败,需要重试机制
   - 测试结果需要持久化存储
   - LLM 分析结果需要人工验证

4. **扩展性**
   - Agent 架构支持添加更多工具
   - 测试步骤支持自定义扩展
   - 评估标准可配置化
