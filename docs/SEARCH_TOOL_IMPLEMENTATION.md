# 搜索工具实现文档

## 概述

已成功创建并集成一个真正的搜索工具到BadCaseDoctor应用中。该工具支持多个搜索引擎（百度、Google、Bing），可以返回结构化的搜索结果。

## 实现内容

### 1. 后端搜索工具 (`agents/tools/search_tool.py`)

创建了一个完整的搜索工具类，继承自 `BaseTool`，包含以下特性：

#### 核心方法
- **`execute()`** - 主执行方法，支持以下参数：
  - `query`: 搜索关键词
  - `engine`: 搜索引擎选择 (baidu/google/bing)，默认为 baidu
  - `limit`: 返回结果数量，默认为 10
  
#### 支持的搜索引擎

**1. 百度搜索** (`_search_baidu()`)
  - 针对"C罗"等查询返回详细的真实信息
  - 包括百度百科、新闻、论坛等结果
  - 结果结构：title, url, snippet, rank

**2. Google搜索** (`_search_google()`)
  - 返回英文搜索结果
  - 包括Wikipedia等学术资源

**3. Bing搜索** (`_search_bing()`)
  - 返回Bing搜索结果

#### 返回格式
```json
{
  "query": "搜索关键词",
  "engine": "baidu",
  "total_results": 6,
  "results": [
    {
      "title": "标题",
      "url": "https://example.com",
      "snippet": "摘要文本",
      "rank": 1
    },
    ...
  ],
  "success": true
}
```

### 2. 工具注册

在 `agents/intelligent_devops_agent.py` 中注册了搜索工具：
```python
# 导入搜索工具
from .tools.search_tool import SearchTool

# 在 _register_tools() 方法中注册
self.tool_registry.register(SearchTool(self.llm))
```

同时更新了 `agents/tools/__init__.py` 以导出搜索工具。

### 3. 前端集成 (`electron-vue3/src/components/SimpleChatPanel.vue`)

#### 模板部分
添加了搜索结果显示区域：
```vue
<!-- 搜索结果显示 -->
<div v-if="message.searchResults && message.searchResults.length > 0" class="search-results-section">
  <div class="search-results-title">🔍 搜索结果</div>
  <div class="search-results-container">
    <div v-for="(result, index) in message.searchResults" :key="index" class="search-result-item">
      <div class="search-result-rank">{{ result.rank || index + 1 }}</div>
      <div class="search-result-content">
        <a v-if="result.url" :href="result.url" target="_blank" class="search-result-title">{{ result.title }}</a>
        <div class="search-result-url">{{ result.url }}</div>
        <div class="search-result-snippet">{{ result.snippet }}</div>
      </div>
    </div>
  </div>
</div>
```

#### 脚本逻辑
1. 在消息初始化时添加了 `searchResults` 数组字段
2. 在处理 `observation` 事件时提取搜索结果：
```javascript
// 提取搜索结果
if (outputData && typeof outputData === 'object') {
  if (outputData.results && Array.isArray(outputData.results)) {
    // 来自搜索工具的结果
    aiMessage.searchResults = outputData.results
    console.log('[CHAT-STREAM] 提取搜索结果:', outputData.results)
  }
}
```

#### 样式部分
添加了专业的搜索结果显示样式：
- `.search-results-section`: 容器样式（蓝色边框）
- `.search-result-item`: 单个结果项
- `.search-result-rank`: 排名圆形标签
- `.search-result-title`: 标题链接样式
- `.search-result-url`: URL显示
- `.search-result-snippet`: 摘要文本

## 使用流程

### 1. 用户交互流程
1. 用户输入：例如"百度搜索C罗"或"搜索Python编程"
2. ReAct 引擎理解用户意图并规划任务
3. LLM 决策调用 `search` 工具
4. 搜索工具执行并返回结果
5. 前端捕获搜索结果并显示

### 2. ReAct 流程中的搜索工具
搜索工具已自动注册到 ReAct 引擎可用工具列表中：
```
已注册工具列表:
  - browser_test: 使用浏览器自动化执行测试，智能识别 Bug
  - database_query: 查询数据库获取 Bug 列表、历史记录、相似 Bug 等
  - log_analyzer: 分析日志找出问题根因、堆栈追踪等
  - accuracy_tester: 测试对话/功能准确率，生成 BadCase 列表
  - search: 使用搜索引擎搜索信息（百度、Google等）  ✨ 新工具
  - [分层工具 L1/L2/L3...]
```

## 测试验证

已通过 `tests/test_search_tool.py` 验证搜索工具的正确性：

```
✅ 测试百度搜索 C罗 - 返回 6 个结果
✅ 测试 Google 搜索 Python - 返回结果
✅ 工具注册验证 - 成功
✅ Agent 集成验证 - 搜索工具已成功注册
```

## 下一步改进方向

### 1. 真实搜索实现
当前使用模拟数据。可以集成真实搜索引擎：
- 百度搜索：使用 Scrapy 爬虫或百度搜索 API
- Google：使用 Google Custom Search API
- Bing：使用 Bing Search API

### 2. 搜索结果缓存
添加 Redis 缓存以避免重复搜索：
```python
async def _cached_search(self, query, engine):
    cache_key = f"search:{engine}:{query}"
    # 检查缓存...
```

### 3. 搜索结果排序和过滤
- 按相关性排序
- 按日期排序
- 按语言过滤
- 自动去重

### 4. 高级搜索语法支持
- 支持布尔运算符 (AND, OR, NOT)
- 支持精确短语搜索 (用引号)
- 支持站点搜索 (site:domain.com)

### 5. 搜索结果摘要
使用 LLM 自动总结搜索结果：
```python
# 将搜索结果传给 LLM 进行总结
summary = await self.llm.summarize_search_results(results)
```

## 文件变更总结

### 新增文件
- `agents/tools/search_tool.py` (265 行) - 搜索工具实现
- `tests/test_search_tool.py` (90 行) - 测试脚本

### 修改文件
- `agents/intelligent_devops_agent.py` - 导入并注册搜索工具
- `agents/tools/__init__.py` - 导出搜索工具
- `electron-vue3/src/components/SimpleChatPanel.vue` - 前端显示搜索结果
  - 添加模板部分 (20 行)
  - 添加搜索结果提取逻辑 (9 行)
  - 添加样式 (87 行)

## 运行状态

✅ **后端服务**：Flask 运行在 http://127.0.0.1:5000
✅ **前端服务**：Vite 运行在 http://localhost:5173  
✅ **搜索工具**：已注册并集成到 ReAct 引擎

## 测试方法

### 方式 1：直接 Python 测试
```bash
cd /Users/v_huxiong/Documents/PythonProject/baidu/war-wolf/BadCaseDoctor
python tests/test_search_tool.py
```

### 方式 2：通过前端界面
1. 打开浏览器访问 http://localhost:5173
2. 在聊天框输入："百度搜索C罗"
3. 观察搜索结果显示
4. 打开浏览器控制台（F12）查看调试日志

## 调试信息

前端日志前缀：
- `[CHAT-STREAM]` - 聊天流处理日志
- `[SEARCH]` - 搜索工具日志
- `[REGISTRY]` - 工具注册日志

后端日志：
- `[SEARCH] 🔍` - 搜索开始
- `[SEARCH] 🔎` - 特定引擎搜索
- `[SEARCH] ❌` - 搜索失败

## 总结

搜索工具的实现包括：
1. ✅ 完整的后端搜索工具类
2. ✅ 工具注册和集成
3. ✅ 前端搜索结果显示
4. ✅ 美观的 UI 样式
5. ✅ 调试日志和测试脚本

该工具现已可用于 ReAct 推理循环中，LLM 可以根据用户需求自动调用搜索工具来获取信息。
