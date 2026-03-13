# 需求3：大模型调用采集 SDK（Java+Python）→ Prometheus → Badcase 因素分析

**状态**：待办  
**优先级**：高  
**创建日期**：2026-03-11

---

## 背景 / 问题

- 在使用大模型 API 的过程中，会出现 badcase（结果不符合预期/不可用/不稳定等）。
- 需要通过**统一的指标采集与观测**，沉淀“影响 badcase 的 5 大因素”，用于后续归因、对比、预警与优化。
- 目标是提供 **Java 版 SDK** 与 **Python 版 SDK**：业务侧接入后自动采集指标，上报到 Prometheus；本项目再从 Prometheus 读取数据用于分析与展示。

## 需求描述

### 1) 采集范围：影响 badcase 的 5 大因素（可配置）

> 以下为建议的 5 大因素维度。若你已有既定 5 项名称/定义，可在实现前替换为你的最终口径。

1. **模型与参数因素**  
   - model（模型名）、temperature、top_p、max_tokens、presence/frequency penalty、tools/function-call 开关等
2. **输入因素**  
   - prompt/上下文长度（token 数）、输入类型（对话/补全/多模态）、系统提示版本、模板 id
3. **外部依赖因素**  
   - 检索/数据库/工具调用次数与耗时、命中率、失败率（RAG/工具链对结果影响）
4. **服务稳定性因素**  
   - API 延迟分布（p50/p95/p99）、超时率、限流/429、5xx、重试次数
5. **输出质量因素（与 badcase 标签关联）**  
   - 业务侧判定：success/failed/badcase_type、人工反馈、自动校验失败原因、解析失败等

### 1.1) 统一事件模型（SDK 内部）

> Prometheus 只存统计指标；SDK 内部仍需要一个“单次调用事件”的结构，用于把同一次调用的各字段映射到不同指标与 label。

建议 SDK 内部事件字段（Java/Python 对齐，允许缺省）：

- **基础字段**
  - `app`：服务/应用名（必填）
  - `env`：dev/stage/prod（必填）
  - `provider`：openai/qianfan/zhipu/qwen/...（必填）
  - `endpoint`：chat/completions/embeddings/tools（必填）
  - `model`：模型名（必填，需归一化）
  - `streaming`：true/false
  - `result`：success/fail
  - `error_type`：timeout/http_429/http_5xx/parse_error/...（fail 时建议填）
  - `http_status`：整数（可选）
- **参数因素（低基数）**
  - `temperature_bucket`：如 `t_0_0`/`t_0_2`/`t_0_7`/`t_1_0plus`
  - `top_p_bucket`：如 `p_0_1`/`p_0_9`/`p_1_0`
  - `max_tokens_bucket`：如 `mt_256`/`mt_512`/`mt_1024plus`
  - `tools_enabled`：true/false
- **输入因素（低基数）**
  - `prompt_template_id`：短字符串/枚举（禁止长 id）
  - `prompt_version`：短字符串/数字
  - `input_tokens_bucket`：如 `in_0_512`/`in_512_2k`/`in_2k_8k`/`in_8kplus`
- **外部依赖因素（可选）**
  - `tool_name`：短枚举（仅用于 tool 相关指标）
  - `tool_calls`：整数
  - `retrieval_enabled`：true/false
- **输出质量因素**
  - `badcase_type`：`none`/`hallucination`/`format_error`/`refuse`/`tool_error`/...（可扩展，建议枚举化）
  - `output_tokens_bucket`：如 `out_0_256`/`out_256_1k`/`out_1kplus`

### 2) SDK 形态与接入方式

#### Java SDK（Micrometer）

- 使用 **Micrometer** 作为采集框架（Counter/Timer/DistributionSummary/Gauge）。
- 输出方式：提供 `PrometheusMeterRegistry`（或适配 Spring Boot Actuator `/actuator/prometheus`）。
- 支持在调用大模型 API 的关键路径埋点：
  - 请求开始/结束计时
  - HTTP 状态码、异常类型、重试与退避
  - token 用量（input/output/total）
  - badcase 标签（由业务侧/本项目判定后回填或即时标注）
 - **SSE/流式输出采集**（Streaming）：
   - `time_to_first_token`（首 token 延迟 / 首帧延迟）
   - `stream_duration`（从开始到完成的流式总耗时）
   - `stream_chunks_total`（收到的 chunk 数）
   - `stream_bytes_total`（可选：累计字节数）
   - `finish_reason`（可选：停止原因，注意 label 基数可控）
   - `stream_interrupted_total`（流中断/提前结束计数）

#### Python SDK（Prometheus client 类库）

- 使用 Python 侧 Prometheus 生态（例如 `prometheus_client` 或等价库）暴露指标端点。
- 提供装饰器/上下文管理器两种接入方式：
  - `@llm_observe(...)` 装饰器：包裹一次 LLM 调用
  - `with llm_span(...):`：更灵活地记录分段耗时（检索、工具调用、模型调用等）
 - **SSE/流式输出采集**：
   - 在迭代消费 SSE event/chunk 时累计：chunk 数、字节数、输出 token（若可得）
   - 在收到第一段有效 content 时记录 `time_to_first_token`
   - 在流结束时记录 `stream_duration` 与 `finish_reason`（若 API 提供）

### 2.1) SDK API 设计（建议，开发对齐点）

> 以“最少侵入、能落地”为原则：业务侧只需在调用 LLM 前后补充少量字段；SDK 封装计时、异常处理、bucket 化与指标上报。

#### Python（建议对外 API）

- `llm_observe(...)`：装饰器，适用于“一个函数=一次 LLM 调用”
- `llm_span(...)`：上下文管理器，适用于“一次请求中包含检索/工具/模型多段”
- `observe_stream(...)`：对 async/sync 流式迭代器做包装，自动记录首 token/总耗时/chunk 计数/中断
- `set_badcase_label(request_key, badcase_type)`（可选）：当 badcase 标签需要在调用结束后由其他流程标注时使用（见 2.2）

必要参数（最小集合）：`app, env, provider, endpoint, model, streaming`  
可选参数：`prompt_template_id, prompt_version, temperature, top_p, max_tokens, tools_enabled, input_tokens, output_tokens, badcase_type`

#### Java（建议对外 API）

- `LlmObservation.start(ctx)` / `LlmObservation.stop(ctx, result)`：显式 start/stop
- 或 `LlmObserver.observe(ctx, Supplier<T> call)`：函数式包裹
- `StreamObserver.wrap(Publisher/Iterator, ctx)`：对流式输出的订阅/迭代做包装
- `BadcaseMarker.mark(requestKey, badcaseType)`（可选）：异步标注（见 2.2）

### 2.2) Badcase 标签回填（两种模式）

- **同步标注（推荐优先支持）**
  - 业务调用方当场决定 `badcase_type`（如自动校验失败/解析失败/明确拒答等），直接作为 label 上报。
- **异步标注（可选增强）**
  - 调用结束时先按 `badcase_type=none` 上报；后续人工/系统标注 badcase 时，额外上报一条“标注事件计数”指标（见 3.2 的 `badcase_marks_total`），用于分析 badcase 分布。
  - 注意：Prometheus 不适合“更新历史样本标签”，因此异步模式用“标注计数”表达，而不是回写旧样本。

### 3) 指标设计（Prometheus 维度、命名与标签）

#### 指标命名规范（建议）

- 统一前缀：`badcase_llm_` 或 `bdc_llm_`
- 关键指标建议：
  - `*_requests_total`（Counter）：请求数
  - `*_errors_total`（Counter）：错误数（按异常类型/状态码）
  - `*_duration_seconds`（Histogram/Timer）：耗时
  - `*_tokens_total`（Counter）：token 用量
  - `*_badcase_total`（Counter）：badcase 次数（按 badcase_type）
  - `*_tool_calls_total`（Counter）：工具调用次数（可按 tool_name）
  - `*_retrieval_duration_seconds`（Histogram）：检索耗时（可选）
  - **流式相关（SSE）**：
    - `*_time_to_first_token_seconds`（Histogram/Timer）：首 token/首帧延迟
    - `*_stream_duration_seconds`（Histogram/Timer）：流式总耗时
    - `*_stream_chunks_total`（Counter）：chunk 数
    - `*_stream_interrupted_total`（Counter）：流中断次数

#### 必备标签（最小集合，避免爆炸）

- `app`：调用方应用/服务名
- `env`：环境（dev/stage/prod）
- `provider`：供应商（qianfan/openai/zhipu/qwen/…）
- `model`：模型名（注意基数，必要时做归一）
- `endpoint`：接口类型（chat/completions/embeddings/tools）
- `result`：success/fail
- `badcase_type`：无/类型（仅在标注时出现；可用 `none`）
- `streaming`：true/false（是否流式）

> 约束：严禁把原始 prompt、用户文本、长 id（如 request_id）直接作为 Prometheus label，防止高基数与隐私泄露。

### 3.1) 指标清单（建议必做）

> Java 与 Python 必须做到“同名同口径”，否则后续看板与分析会碎片化。

基础指标（必做）：

- `bdc_llm_requests_total{app,env,provider,endpoint,model,streaming,result}`（Counter）
- `bdc_llm_errors_total{app,env,provider,endpoint,model,streaming,error_type,http_status}`（Counter）
- `bdc_llm_duration_seconds{app,env,provider,endpoint,model,streaming,result}`（Histogram/Timer）
- `bdc_llm_tokens_total{app,env,provider,endpoint,model,kind}`（Counter）
  - `kind ∈ {input,output,total}`（避免 3 个指标名）
- `bdc_llm_badcase_total{app,env,provider,endpoint,model,streaming,badcase_type}`（Counter）
  - 若同步标注：每次调用都打一个 `badcase_type`（默认 `none`）

流式指标（如支持 streaming，必做）：

- `bdc_llm_time_to_first_token_seconds{app,env,provider,endpoint,model,result}`（Histogram/Timer）
- `bdc_llm_stream_duration_seconds{app,env,provider,endpoint,model,result}`（Histogram/Timer）
- `bdc_llm_stream_chunks_total{app,env,provider,endpoint,model}`（Counter）
- `bdc_llm_stream_interrupted_total{app,env,provider,endpoint,model,reason}`（Counter）
  - `reason` 建议枚举：`client_cancel`/`upstream_close`/`timeout`/`error`

外部依赖（可选，但建议做至少 tool_calls_total）：

- `bdc_llm_tool_calls_total{app,env,provider,endpoint,model,tool_name,result}`（Counter）
- `bdc_llm_retrieval_duration_seconds{app,env,provider,endpoint,model,result}`（Histogram）

异步标注（可选增强，配合 2.2）：

- `bdc_llm_badcase_marks_total{app,env,provider,endpoint,model,streaming,badcase_type,source}`（Counter）
  - `source` 建议枚举：`human`/`auto`/`qa`

### 3.2) Bucket 化与 label 基数控制（强约束）

- **数值参数禁止直接做 label**
  - `temperature/top_p/max_tokens/input_tokens/output_tokens` 必须映射成有限 bucket（见 1.1 示例字段）。
- **model 归一化**
  - 对带版本/日期的模型名做归一（例如把 `gpt-4.1-2026-02-15` 归为 `gpt-4.1`），避免 label 膨胀。
- **badcase_type 枚举化**
  - 必须是短枚举；新增类型需要同步到本项目字典（用于展示与聚合）。
- **禁止高基数 label**
  - `request_id/user_id/session_id/prompt_hash/raw_error_message` 一律禁止。

### 4) Prometheus 接入与本项目读取方式

- **采集链路**：业务侧（Java/Python SDK 暴露 `/metrics`）→ Prometheus scrape → 本项目查询 Prometheus。
- 本项目从 Prometheus 读取方式：
  - 通过 Prometheus HTTP API（PromQL 查询）读取时间序列
  - 分析“5 大因素”与 badcase 的相关性：按维度分组统计 badcase_rate、延迟分位、错误率、token 分布等
- 输出形态（本项目侧）：
  - 因素看板：按时间、模型、供应商、参数 bucket、输入规模 bucket
  - badcase 归因：badcase_type topN + 相关因素 topN（可先用简单统计/规则，后续再做 ML）

### 4.1) PromQL（本项目查询示例，可直接用于实现）

> 下面 PromQL 用于说明“本项目如何算”。实际实现时建议把 `${app}/${env}` 等作为变量。

- **请求量（QPS）**
  - `sum(rate(bdc_llm_requests_total{env="$env",app="$app"}[5m])) by (provider,model,endpoint,streaming)`
- **错误率**
  - `sum(rate(bdc_llm_errors_total{env="$env",app="$app"}[5m])) / sum(rate(bdc_llm_requests_total{env="$env",app="$app"}[5m]))`
- **badcase 率（同步标注模式）**
  - `sum(rate(bdc_llm_badcase_total{env="$env",app="$app",badcase_type!="none"}[15m])) / sum(rate(bdc_llm_requests_total{env="$env",app="$app"}[15m]))`
- **耗时 p95（Histogram）**
  - `histogram_quantile(0.95, sum(rate(bdc_llm_duration_seconds_bucket{env="$env",app="$app"}[10m])) by (le,provider,model,endpoint,streaming))`
- **TTFT p95（流式）**
  - `histogram_quantile(0.95, sum(rate(bdc_llm_time_to_first_token_seconds_bucket{env="$env",app="$app"}[10m])) by (le,provider,model,endpoint,model))`
- **token 单次均值（近似）**
  - `sum(rate(bdc_llm_tokens_total{env="$env",app="$app",kind="total"}[10m])) / sum(rate(bdc_llm_requests_total{env="$env",app="$app"}[10m]))`

### 4.2) “5 大因素”分析口径（本项目侧计算）

> 第一版以“分组对比 + topN”即可，不引入复杂模型。

- **模型与参数因素**：按 `provider/model/temperature_bucket/top_p_bucket/max_tokens_bucket/tools_enabled` 分组，输出：`badcase_rate`、`p95_latency`、`error_rate`、`avg_tokens`
- **输入因素**：按 `prompt_template_id/prompt_version/input_tokens_bucket` 分组输出同上
- **外部依赖因素**：按 `tool_name` 或 `retrieval_enabled` 分组；输出工具错误率、工具调用次数分布与 badcase 相关性（用分组 badcase_rate 对比）
- **服务稳定性因素**：按 `http_status/error_type` 与 `provider/model` 分组输出错误构成；结合 p95/p99 延迟与超时率
- **输出质量因素**：按 `badcase_type` 输出 topN，并回溯关联维度（例如某 badcase_type 在某 model/输入 bucket 下显著升高）

### 5) 数据与隐私/安全

- 不采集/不上传原始 prompt、原始输出全文（如需回放另做审计系统，不走 Prometheus）。
- 支持采集“长度/哈希/模板 id/版本号”等脱敏信息。
 - **SSE 流式内容同样不采集全文**：仅采集统计量（首 token 时间、chunk 数、耗时、错误/中断、token 计数等）。

## 约束规则

- Java 必须使用 Micrometer 体系，指标落到 Prometheus 可抓取端点。
- Python 使用 Prometheus 生态的等价库暴露指标端点。
- Prometheus 作为统一落点，本项目只从 Prometheus 读取，不直接从各 SDK 拉取私有格式。
- 标签基数必须可控，避免造成 Prometheus 压力与查询不可用。

## 验收标准

- [ ] 提供 **Java SDK**：可在一次 LLM 调用中采集请求数、错误数、耗时、token、badcase 标签等核心指标，并通过 Prometheus 端点暴露。
- [ ] 提供 **Python SDK**：能力与 Java 对齐（至少核心指标一致），并通过 Prometheus 端点暴露。
- [ ] Prometheus 能成功抓取两端指标（在同一 Prometheus 实例中可区分 app/env/provider/model 等）。
- [ ] 本项目能从 Prometheus 读取指标并生成“badcase 影响因素（5 大因素）”的分析结果（至少包含按维度分组的 badcase_rate 与耗时分位/错误率）。

## 开发拆解（建议）

> 用于排期与分工；不限制你现有工程组织方式。

- **SDK（Python）**
  - 指标注册与 `/metrics` 暴露（与现有 Flask/FastAPI 集成方式任选）
  - `llm_observe/llm_span/observe_stream` 基础能力
  - bucket 化与 label 归一化
  - 异常分类（error_type）与 http_status 提取
- **SDK（Java）**
  - Micrometer 指标定义与 Prometheus 端点暴露（Spring Boot Actuator 优先）
  - Timer/Counter/Histogram 对齐 Python 的口径
  - Streaming 观测（TTFT/stream_duration/chunks/interrupted）
- **Prometheus**
  - scrape 配置与 target 区分（app/env）
  - 基础告警（可选）：错误率、p95 延迟、badcase_rate 异常升高
- **本项目（BadCaseDoctor）**
  - Prometheus HTTP API client（PromQL 查询封装）
  - 看板/接口：因素聚合 topN、时间范围查询、筛选（app/env/provider/model）
  - 口径固化：badcase_type 枚举与维度字典（前后端一致）

## 备注

- “5 大因素”的最终口径建议在实现前固化为字段清单与枚举，并提供可扩展能力（新增维度不破坏历史指标）。
- 后续可扩展：Trace（OpenTelemetry）与日志（结构化事件）联动，但本需求以 Prometheus 指标为主。
