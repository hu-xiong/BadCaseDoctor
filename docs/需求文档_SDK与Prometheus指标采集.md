# 需求文档：BadCase 指标采集 SDK 与 Prometheus 集成

**状态**：待办  
**优先级**：高  
**创建日期**：2026-03-22

---

## 1. 概述

### 1.1 背景

对话变成 BadCase 受多种因素影响，需通过统一指标采集与观测，沉淀「影响 BadCase 的五大因素」，用于归因、对比、预警与优化。目标是提供 **Java SDK** 与 **Python SDK**：业务侧接入后自动采集对话相关指标，上报到 Prometheus；本项目（BadCase Doctor）再从 Prometheus 读取数据用于 BadCase 分析。

### 1.2 目标

1. 实现 Java、Python 双语言 SDK，采集五大因素相关指标
2. 使用 Prometheus 作为统一指标接收端
3. 通过 **Trace ID** 将单次对话下的所有指标关联（模型调用、工具调用、工作流步骤）
4. 支持多工具 / 工作流场景下的上下文传递与 Trace
5. 提供 SSE 流式输出采集插件，采集答案相关指标
6. 本项目从 Prometheus 获取指标，支撑 BadCase 分析看板

---

## 2. BadCase 五大因素

| 因素 | 说明 | 采集内容 |
|------|------|----------|
| **模型与参数因素** | 调用配置影响结果质量 | model、temperature、top_p、max_tokens、tools_enabled 等 |
| **输入因素** | 提示词与上下文质量 | 提示词模板/版本、输入 token 规模、召回文档数量/质量 |
| **外部依赖因素** | RAG / 工具链对结果的影响 | 检索耗时、命中率、工具调用次数、工具失败率 |
| **服务稳定性因素** | 基础设施稳定性 | API 延迟、超时率、限流 429、5xx、重试次数 |
| **输出质量因素** | 与 BadCase 标签关联 | 业务侧判定 success/failed/badcase_type、解析失败等 |

---

## 3. 核心设计

### 3.1 Trace ID 与指标关联

所有指标必须能通过 **统一的 Trace ID（conversation_id / request_id）** 关联到同一对话：

- **conversation_id**：一次用户会话（可能包含多轮）的唯一标识
- **request_id**：单次请求（一次模型调用 / 一次工具调用）的唯一标识
- **span_id**：工作流中单步的标识，用于父子关系

**关联规则**：

- 同一对话下：`conversation_id` 相同
- 一次对话可能触发多次模型调用、多次工具调用 → 各次用 `request_id` 区分
- 多工具 / 工作流：通过 **span_id** 与 **parent_span_id** 组成 trace 树

**Prometheus 约束**：`conversation_id`、`request_id` 等高基数 ID 不得直接作为 Prometheus label（易导致基数爆炸）。SDK 内部使用这些 ID 做事件聚合，对外仅输出低基数的 `conversation_id_bucket`（如按时间分桶）或通过 **OpenTelemetry / 日志** 做细粒度关联，Prometheus 只存统计类指标。

**可选方案**：若必须按单次对话做分析，可单独建设「事件存储」或「日志系统」，与 Prometheus 的时序指标互补；本需求以 Prometheus 统计指标为主。

### 3.2 上下文传递与 Trace（多工具 / 工作流）

当一次对话涉及 **多个工具调用** 或 **工作流** 时：

1. **上下文传递**：使用框架的 Context 传递能力（如 Java 的 `ThreadLocal` / `Micrometer Tracing`，Python 的 `contextvars`）在调用链中传递 `conversation_id`、`request_id`、`span_id`、`parent_span_id`
2. **Trace 树**：将一次对话的所有步骤组织成 trace 树，便于在 Prometheus / 分析侧按「对话-步骤」维度聚合
3. **工作流场景**：工作流中每一步（模型调用、工具调用）打上 `workflow_id`、`workflow_step` 等低基数 label，在 Prometheus 中可还原「工作流级」的耗时与 badcase 分布

**技术选型建议**：

- **Java**：Micrometer Tracing（与 Micrometer 指标集成良好），或 OpenTelemetry Java
- **Python**：`opentelemetry-api` + `opentelemetry-sdk`，或 `contextvars` 自实现轻量 context 传递

### 3.3 采集内容清单

| 类别 | 采集项 | 存储方式 | 说明 |
|------|--------|----------|------|
| **模型参数** | model、temperature、top_p、max_tokens、tools_enabled | Prometheus label（bucket 化） | 严禁原始长值做 label |
| **提示词** | prompt_template_id、prompt_version、input_tokens_bucket | Prometheus label | 不采集原文，仅模板/版本/规模 |
| **召回文档** | retrieval_count、retrieval_duration_seconds、retrieval_hit_rate | Prometheus 指标 | 统计量，不存文档内容 |
| **答案** | output_tokens_bucket、stream_chunks、time_to_first_token、finish_reason | Prometheus 指标 | 通过 SSE 插件采集，不存原文 |
| **工具调用** | tool_name、tool_calls、tool_duration、tool_result | Prometheus label/指标 | 工具名、次数、耗时、成功/失败 |
| **工作流** | workflow_id、workflow_step、step_duration | Prometheus label/指标 | 工作流级 trace |

---

## 4. 技术方案

### 4.1 Java SDK（Micrometer）

- **采集框架**：Micrometer
- **输出**：`PrometheusMeterRegistry` 或 Spring Boot Actuator `/actuator/prometheus`
- **Trace**：Micrometer Tracing 或 OpenTelemetry，用于上下文传递与 span 关联

**核心能力**：

- 请求开始/结束计时
- HTTP 状态码、异常类型、重试
- Token 用量（input/output/total）
- BadCase 标签（同步/异步标注）
- SSE 流式：time_to_first_token、stream_duration、stream_chunks、stream_interrupted

### 4.2 Python SDK

- **采集框架**：`prometheus_client` 或与 Micrometer 对等的 Python 生态（如 `prometheus_client` + `opentelemetry-api`）
- **输出**：暴露 `/metrics` 端点（Flask/FastAPI 等可挂载）

**核心能力**：

- `llm_observe` 装饰器：包裹单次 LLM 调用
- `llm_span` 上下文管理器：支持检索 / 工具 / 模型分段记录
- `observe_stream`：包装 SSE 流式迭代器，自动记录 TTFT、chunk 数、中断
- 上下文传递：`contextvars` 或 OpenTelemetry 传递 trace 信息

### 4.3 接入方式：开箱即用（简单易用原则）

用户引用 SDK 时应做到**零配置或极简配置**，无需手写大量埋点代码。

#### Java：Spring Boot Starter + 自动配置（Auto-configuration）

- **机制**：Spring Boot **Starter** 依赖 + **Auto-configuration**（`@Configuration` + `@ConditionalOnClass` / `@ConditionalOnProperty`）
- **接入步骤**：
  1. 引入依赖：`badcase-sdk-spring-boot-starter`
  2. 可选：在 `application.yml` 中配置 `app`、`env`、`enabled` 等
  3. 启动后自动注册 `BadCaseCollector`、暴露 `/actuator/prometheus`（或与现有 Actuator 集成）
- **效果**：用户无需写任何初始化代码，框架自动装配 MeterRegistry、拦截器或 AOP 切面，对常见 LLM 调用路径做自动埋点（若支持）
- **参考**：`spring-boot-starter-actuator`、`micrometer-registry-prometheus` 的用法

```xml
<!-- 用户仅需添加依赖 -->
<dependency>
    <groupId>com.badcase</groupId>
    <artifactId>badcase-sdk-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

```yaml
# 可选配置，有默认值
badcase:
  sdk:
    enabled: true
    app: my-llm-service
    env: prod
```

#### Python：类似 Starter 的「即插即用」机制

- **机制**：采用与 Java Starter 对等的**自动装配**思路，常见做法：
  - **框架集成包**：`badcase-sdk[fastapi]`、`badcase-sdk[flask]`、`badcase-sdk[django]`，安装后通过 middleware / 中间件自动挂载 `/metrics` 与埋点
  - **环境变量驱动**：`BADCASE_SDK_APP`、`BADCASE_SDK_ENV` 等，`import badcase_sdk` 时自动从环境变量初始化
  - **显式一键安装**：`badcase_sdk.install(app=fastapi_app)` 或 `badcase_sdk.auto_instrument()`，一次调用完成所有注册
- **接入步骤**：
  1. `pip install badcase-sdk[fastapi]`（或 flask/django）
  2. 在应用入口调用 `badcase_sdk.install(app)` 或依赖 `auto_instrument()` 自动发现
  3. 可选：通过环境变量或 `badcase_sdk.init(app=..., env=...)` 覆盖配置
- **效果**：与 Java 类似，用户最小化代码改动即可接入

```python
# 方式一：框架集成，一行挂载
from fastapi import FastAPI
import badcase_sdk

app = FastAPI()
badcase_sdk.install(app)  # 自动注册 /metrics、中间件

# 方式二：环境变量 + 自动装配（零代码）
# 设置 BADCASE_SDK_APP=my_app BADCASE_SDK_ENV=prod
# import badcase_sdk  # 自动 init
```

```bash
pip install badcase-sdk[fastapi]
```

### 4.4 SSE 采集插件

针对流式输出（SSE）的专用采集逻辑：

| 指标 | 类型 | 说明 |
|------|------|------|
| `bdc_llm_time_to_first_token_seconds` | Histogram | 首 token / 首帧延迟 |
| `bdc_llm_stream_duration_seconds` | Histogram | 从开始到流结束的总耗时 |
| `bdc_llm_stream_chunks_total` | Counter | 收到的 chunk 数 |
| `bdc_llm_stream_bytes_total` | Counter | 累计字节数（可选） |
| `bdc_llm_stream_interrupted_total` | Counter | 流中断次数（按 reason 分：client_cancel、upstream_close、timeout、error） |
| `bdc_llm_finish_reason` | Counter | 停止原因（stop、length、tool_calls 等，枚举化） |

**采集时机**：

- 迭代消费 SSE event/chunk 时累计 chunk 数、字节数、output token（若 API 提供）
- 收到第一段有效 content 时记录 `time_to_first_token`
- 流结束时记录 `stream_duration` 与 `finish_reason`

---

## 5. 指标设计（Prometheus）

### 5.1 命名规范

- 统一前缀：`bdc_llm_` 或 `badcase_llm_`
- 格式：`{prefix}_{metric_name}`

### 5.2 必备指标

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `bdc_llm_requests_total` | Counter | app, env, provider, endpoint, model, streaming, result | 请求数 |
| `bdc_llm_errors_total` | Counter | app, env, provider, endpoint, model, error_type, http_status | 错误数 |
| `bdc_llm_duration_seconds` | Histogram | app, env, provider, endpoint, model, streaming, result | 耗时 |
| `bdc_llm_tokens_total` | Counter | app, env, provider, endpoint, model, kind | kind: input/output/total |
| `bdc_llm_badcase_total` | Counter | app, env, provider, endpoint, model, streaming, badcase_type | BadCase 计数 |
| `bdc_llm_time_to_first_token_seconds` | Histogram | app, env, provider, endpoint, model, result | 首 token 延迟 |
| `bdc_llm_stream_duration_seconds` | Histogram | app, env, provider, endpoint, model, result | 流式总耗时 |
| `bdc_llm_stream_chunks_total` | Counter | app, env, provider, endpoint, model | chunk 数 |
| `bdc_llm_stream_interrupted_total` | Counter | app, env, provider, endpoint, model, reason | 流中断 |
| `bdc_llm_tool_calls_total` | Counter | app, env, provider, endpoint, model, tool_name, result | 工具调用 |
| `bdc_llm_retrieval_duration_seconds` | Histogram | app, env, provider, model, result | 检索耗时 |
| `bdc_llm_retrieval_docs_total` | Counter | app, env, provider, model | 召回文档数（可选） |

### 5.3 工作流 Trace 指标

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `bdc_llm_workflow_steps_total` | Counter | app, env, workflow_id, workflow_step, step_type, result | 工作流步骤计数 |
| `bdc_llm_workflow_duration_seconds` | Histogram | app, env, workflow_id, workflow_step, step_type | 工作流单步耗时 |

### 5.4 Label 基数控制（强约束）

- **数值类**：temperature、top_p、max_tokens、input_tokens、output_tokens 必须 bucket 化（如 `t_0_0`、`t_0_7`、`in_512_2k`、`out_256_1k`）
- **model**：归一化（如 `gpt-4.1-2026-02-15` → `gpt-4.1`）
- **badcase_type**：使用短枚举（none、hallucination、format_error、refuse、tool_error 等）
- **禁止**：request_id、user_id、session_id、原始 prompt、原始输出、长 hash 作为 label

---

## 6. 数据流与集成

### 6.1 采集链路

```
业务应用 (Java/Python)
    │
    ├─ SDK 埋点：模型调用、工具调用、工作流步骤、SSE 流
    ├─ 上下文传递：conversation_id、span_id（用于内部关联）
    │
    ▼
/metrics 端点 (Prometheus 格式)
    │
    ▼
Prometheus (scrape)
    │
    ▼
BadCase Doctor 项目
    │
    ├─ Prometheus HTTP API（PromQL 查询）
    └─ 分析：五大因素、badcase_rate、延迟分位、错误率、工作流 trace
```

### 6.2 本项目（BadCase Doctor）读取方式

- 通过 Prometheus HTTP API 执行 PromQL 查询
- 按 app、env、provider、model、time_range 等维度聚合
- 输出：因素看板、BadCase 归因、工作流 trace 视图

**示例 PromQL**：

```promql
# 请求量 QPS
sum(rate(bdc_llm_requests_total{env="$env",app="$app"}[5m])) by (provider,model,endpoint,streaming)

# 错误率
sum(rate(bdc_llm_errors_total{env="$env",app="$app"}[5m])) 
/ sum(rate(bdc_llm_requests_total{env="$env",app="$app"}[5m]))

# BadCase 率
sum(rate(bdc_llm_badcase_total{env="$env",app="$app",badcase_type!="none"}[15m])) 
/ sum(rate(bdc_llm_requests_total{env="$env",app="$app"}[15m]))

# 耗时 P95
histogram_quantile(0.95, sum(rate(bdc_llm_duration_seconds_bucket{env="$env",app="$app"}[10m])) by (le,provider,model,endpoint,streaming))
```

---

## 7. SDK API 设计建议

### 7.1 Python

```python
# 装饰器：单次 LLM 调用
@llm_observe(app="my_app", env="prod", provider="qwen", model="qwen-plus", streaming=True)
def call_llm(prompt: str):
    ...

# 上下文管理器：多段（检索 + 工具 + 模型）
with llm_span(app="my_app", env="prod", conversation_id="conv_123") as ctx:
    ctx.record_retrieval(count=5, duration=0.1)
    ctx.record_tool_call(tool_name="grep", duration=0.05, result="success")
    result = call_llm(prompt)

# SSE 流包装
async for chunk in observe_stream(stream_iter, ctx):
    yield chunk

# 异步 BadCase 标注
set_badcase_label(request_key="req_xyz", badcase_type="format_error")
```

### 7.2 Java

```java
// 显式 start/stop
LlmObservation obs = LlmObservation.start(ctx);
try {
    return callLlm(prompt);
} finally {
    obs.stop(result, badcaseType);
}

// 函数式包裹
LlmObserver.observe(ctx, () -> callLlm(prompt));

// 流式包装
StreamObserver.wrap(publisher, ctx);

// 工作流步骤
WorkflowTracer.recordStep(workflowId, stepName, duration, result);
```

---

## 8. 开发拆解

| 阶段 | 内容 |
|------|------|
| **Java SDK** | Micrometer 指标、Prometheus 端点、Streaming 观测、**Spring Boot Starter + Auto-configuration** |
| **Python SDK** | 指标注册、`/metrics` 暴露、`llm_observe`/`llm_span`/`observe_stream`、**框架集成包 + install/auto_instrument** |
| **SSE 插件** | 首 token、chunk 数、stream_duration、interrupted、finish_reason |
| **Trace / 工作流** | context 传递、workflow 指标、span 关联 |
| **Prometheus** | scrape 配置、target 区分 |
| **本项目** | Prometheus 查询封装、因素看板、BadCase 归因接口 |

---

## 9. 约束与验收

### 9.1 约束

- Java 必须使用 Micrometer，指标经 Prometheus 端点暴露
- Python 使用 Prometheus 生态（如 `prometheus_client`）暴露指标
- Prometheus 为统一落点，本项目仅从 Prometheus 读取
- Label 基数必须可控，禁止高基数标签
- 不采集原始 prompt、原始输出、召回文档全文；仅采集统计量与脱敏维度

### 9.2 验收标准

- [ ] Java SDK 以 **Spring Boot Starter** 形式提供，用户添加依赖 + 可选配置即可接入，无需手写初始化
- [ ] Python SDK 提供 **框架集成包**（如 `badcase-sdk[fastapi]`）及 `install()` / `auto_instrument()`，接入方式与 Java 对等
- [ ] Java SDK 支持一次 LLM 调用采集请求数、错误数、耗时、token、badcase 标签，并通过 Prometheus 暴露
- [ ] Python SDK 能力与 Java 对齐
- [ ] SSE 插件可采集 TTFT、stream_duration、chunk 数、interrupted
- [ ] 支持多工具 / 工作流场景的 context 传递与 trace 指标
- [ ] 有统一 ID（conversation_id/request_id）在 SDK 内部关联对话各环节
- [ ] Prometheus 可成功抓取两端指标
- [ ] 本项目可从 Prometheus 读取并生成五大因素与 BadCase 归因分析

---

## 10. 备注

- 五大因素口径需在实现前固化为字段清单与枚举，便于前后端一致
- 若需按单次对话细粒度回溯，可另行建设事件存储/日志，与 Prometheus 互补
- 后续可扩展 OpenTelemetry 全链路 Trace，与 Prometheus 指标联动
