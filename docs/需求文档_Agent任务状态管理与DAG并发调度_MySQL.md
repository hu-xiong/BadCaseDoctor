# 需求文档：任务状态管理与并发执行系统（MySQL + DAG）

## 1. 文档目标

本文档定义在 BadCaseDoctor 项目中引入**持久化任务队列**与 **DAG 依赖调度**的产品与技术需求，用于：

- 将每次工具调用抽象为可追踪、可恢复的任务单元；
- 在无依赖或依赖已满足时**并发执行**工具，缩短多步流水线总耗时；
- 服务重启后**恢复**未完成任务，避免状态仅驻留内存；
- 与现有 **ReAct 流式链路（SSE）** 对齐，保证前端可展示任务生命周期。

本文档为**需求与方案约束**；具体类设计、文件路径与完整实现代码属于开发阶段交付物，不在本文展开。

---

## 2. 项目背景与痛点

### 2.1 现状（简述）

- Agent 主循环位于 `agents/react_simplified.py`（及关联路由、SSE 封装）。
- 工具调用在当前架构下以**串行**方式嵌入 ReAct 步骤内执行；任务进度主要依赖进程内状态与 SSE 事件，**进程外不可见、不可恢复**。

### 2.2 待解决问题

| 问题 | 说明 |
|------|------|
| 无法并发 | 无依赖的多工具步骤只能排队执行，浪费 I/O 等待 |
| 状态易失 | 重启后无法接续「进行中」的工具任务 |
| 缺少统一任务视图 | 难以审计参数、结果、错误与耗时 |
| 依赖关系隐含 | 若未来一步拆成多子任务，缺少显式 DAG 表达 |

---

## 3. 范围与非范围

### 3.1 范围内

- 基于 **MySQL** 的任务表设计与 ORM 模型（与现有 Flask-SQLAlchemy 体系一致者优先）。
- **任务创建、状态迁移、依赖就绪判定、调度与执行**（线程池）。
- 应用启动时对 `running` 任务的**恢复策略**（见 6.5）。
- 与 **ReAct 主循环**的集成方式约定：创建任务、等待完成、SSE 事件形态（见第 7 节）。

### 3.2 范围外（可列为后续迭代）

- 跨多机分布式调度（本文默认**单进程单调度器**）。
- 任务优先级队列、公平调度、资源配额（可在 v2 需求中单列）。
- 自动检测并打破循环依赖（**约定由调用方保证 DAG 无环**；系统可记录校验失败原因）。
- 替换现有全部 SSE 协议（仅在兼容前提下**扩展**事件类型或 payload）。

---

## 4. 技术栈约束

| 项 | 要求 |
|----|------|
| 语言 | Python 3.9+ |
| Web | Flask（已有） |
| ORM | SQLAlchemy，优先与 **Flask-SQLAlchemy** 的 `db.session` 生命周期对齐 |
| 并发执行 | `concurrent.futures.ThreadPoolExecutor`（大小可配置，建议 5～10） |
| 数据库 | MySQL（已有实例/连接配置复用） |

---

## 5. 数据模型

### 5.1 表名

`agent_tasks`（若与现有命名空间冲突，可在实现阶段调整为 `react_agent_tasks` 等，**以迁移脚本为准**，本文仍以需求表名为准）。

### 5.2 字段定义

| 字段名 | 类型 | 约束 | 描述 |
|--------|------|------|------|
| `id` | CHAR(36) | PK | UUID 字符串 |
| `name` | VARCHAR(100) | NOT NULL | 工具名称（与工具注册表一致） |
| `status` | ENUM | NOT NULL，默认 `pending` | `pending` / `running` / `done` / `failed` |
| `params` | JSON | 可空 | 工具调用参数（对象） |
| `result` | JSON | 可空 | 成功时的结构化结果 |
| `error` | TEXT | 可空 | 失败时的错误信息（含 traceback 摘要策略由实现约定） |
| `dependencies` | JSON | 可空，默认 `[]` | 所依赖任务的 `id` 列表（UUID 字符串数组） |
| `session_id` | VARCHAR(36) | 可空，建议索引 | 关联对话/会话，便于按会话查询与清理 |
| `created_at` | TIMESTAMP | NOT NULL | 创建时间 |
| `started_at` | TIMESTAMP | 可空 | 开始执行时间 |
| `finished_at` | TIMESTAMP | 可空 | 结束时间 |

### 5.3 索引

- `idx_session`：`session_id`
- `idx_status`：`status`（或与 `session_id` 联合索引，由实现根据查询模式选择）

### 5.4 约束与约定

- `dependencies` 中 ID 必须指向**同表**已存在行；**不允许自依赖**；**不允许环**（由业务/调用方保证；可选在创建时做拓扑校验）。
- 仅当所有依赖任务 `status = done` 时，本任务可被调度为 `running`。
- `dependencies` 为空或 `[]`：视为依赖已满足。

---

## 6. 功能需求

### 6.1 DAG 依赖解析（就绪条件）

对任意 `pending` 任务 `T`：

1. 读取 `T.dependencies`（UUID 列表）。
2. 若列表为空，**就绪**。
3. 若非空：查询这些 `id` 对应记录，**全部**存在且 `status = done` 则**就绪**；否则**不就绪**。
4. 若某依赖 `failed`：实现策略二选一（需在实现/配置中**固定一种**并文档化）：
   - **策略 A（推荐默认）**：依赖失败则本任务永不自动就绪，标记为 `failed` 或 `cancelled`（若扩展状态），并写入 `error`；
   - **策略 B**：仍允许就绪（一般不推荐，除非业务明确）。

本文默认 **策略 A**。

### 6.2 任务创建 `create_task`

**输入**（逻辑参数）：

- `name`：工具名  
- `params`：`dict`  
- `dependencies`：`list[str]`，可选，任务 UUID  
- `session_id`：可选  

**行为**：

- 生成 UUID，写入一行，`status = pending`，`created_at = now`。
- 使用**事务**提交；返回 `task_id`。

**错误处理**：

- 非法 JSON、依赖 ID 不存在、检测到环（若实现校验）→ 抛业务异常或返回错误码，**不写半行**。

### 6.3 调度器（Scheduler）

**职责**：

- 独立**后台线程**（或等价长期运行协程+线程池，实现二选一，默认**守护线程 + 短周期轮询**）。
- 固定周期扫描（如 **100ms**，可配置）：查找可执行的 `pending` 且**依赖就绪**的任务。

**每次调度迭代**：

1. 在**短事务**内查询一批候选 `pending` 任务（可按 `session_id` 或全局，需求默认**全局队列**，过滤条件可配置）。
2. 对每条候选任务做依赖检查（6.1）。
3. 对就绪任务执行**原子抢占**：将 `status` 从 `pending` 更新为 `running`，写入 `started_at`，保证**同一任务不会被重复领取**。
   - 推荐：`UPDATE ... WHERE id=? AND status='pending'` 影响行数为 1 才算成功；或使用 `SELECT ... FOR UPDATE` + 同一事务内更新。
4. 提交事务后，将 `task_id` 提交给线程池 `executor.submit(execute_task, task_id)`。

**停止**：

- 应用关闭时：`stop_event` 置位，调度线程退出循环；线程池 `shutdown(wait=...)` 策略需可配置（见 8.2）。

### 6.4 执行器（Executor）

**输入**：`task_id`。

**行为**：

1. 新开或使用绑定策略的 `db.session`（多线程下**禁止**与 Flask 请求线程共用一个未隔离的 session，需按 Flask-SQLAlchemy 推荐方式处理 `app.app_context()` 与 `scoped_session`）。
2. 根据 `name` 从**现有工具注册表**解析可调用对象，注入 `params`（与当前 `_execute_tool` 语义对齐）。
3. 成功：`status = done`，`result` JSON，`finished_at = now`，`error = NULL`。
4. 失败：`status = failed`，`error` 文本，`finished_at = now`。
5. 全程**事务**提交。

**与 SSE**：

- 执行开始/结束需能通知 ReAct 流（见第 7 节），**不阻塞**数据库提交顺序。

### 6.5 恢复机制

应用启动时：

- 将所有 `status = running` 的任务重置为 `pending`（并可选清空 `started_at` 或写入审计字段），以便调度器重新领取。

**可选增强**（非必须 v1）：

- 记录 `attempt_count`，超过阈值标记 `failed`，避免无限重试。

### 6.6 并发与资源

- 线程池大小**环境变量或配置项**（默认 5～10）。
- 同一 `session_id` 下是否允许并行：默认**允许**（由 DAG 表达依赖）；若产品要求「同会话串行」，需单独需求。

---

## 7. 与 ReAct / SSE 集成需求

### 7.1 集成原则

- **不改变**现有 ReAct 单步语义：一步内模型仍产出一次 decision；若该步需执行工具，则对应**一个或多个**持久化任务。
- 当本步需要**多个无依赖工具**时：可 `create_task` 多次，共享同一 `session_id`，`dependencies` 为空或互为独立；ReAct 侧**等待**这些任务全部进入终态（`done`/`failed`）后再进入 observe / 下一轮。
- 当存在**链式依赖**时：后建任务的 `dependencies` 指向前序任务 id，由调度器自动在满足后启动。

### 7.2 SSE 事件（建议命名，可与现有 wire v1 映射）

需在现有事件体系中**增加或复用** payload 字段（具体 `type` 与 `payload` 键名在实现阶段与 `agents/sse_react_v1.py` 对齐）：

| 时机 | 事件语义 | 最小 payload |
|------|----------|----------------|
| 任务已创建并已入队 | `tool_task_created` | `task_id`, `name`, `session_id`, `dependencies` |
| 任务开始执行 | `tool_task_running` | `task_id`, `name`, `started_at` |
| 任务成功结束 | `tool_task_done` | `task_id`, `result` |
| 任务失败 | `tool_task_failed` | `task_id`, `error` |

（若产品希望与现有 `action_start`/`action_result` 合并，需在评审中二选一，避免前端双轨。）

### 7.3 ReAct 等待策略

- **推荐**：内存中 `asyncio` 与线程池协作，任务完成时由执行器写入队列/Event，流式生成器 `await` 就绪，**避免**同步阻塞事件循环。
- **可接受兜底**：带超时与退避的轮询 DB（性能较差，仅作备选）。

### 7.3.1 浏览器刷新 ≠ 服务端恢复（与 §6.5 区分）

| 维度 | §6.5 服务端重启 | 用户 F5 / 关 Tab（前端） |
|------|----------------|------------------------|
| SSE | 不适用 | **连接断开**；续流靠 **`GET /api/agent/react/buffer`**（见 session 文档 §5.2.1），非原连接续订 |
| `agent_tasks` | `running` → `pending` 可被调度器重领 | 表内可仍为 `running`；**续流主路径是 SSE buffer**，非仅轮询任务表 |
| 前端应展示什么 | — | 刷新后 **buffer 重放 + `bcd:ss:agent` 快照**；终态仍以 **Chat Session 消息** 为准 |
| 可选 API | — | `GET /api/agent/tasks?session_id={react_request_id}` 辅助摘要（需 `REACT_AGENT_TASK_DAG=1`） |

**产品结论（与 session 文档 v0.8/v0.9 对齐）**：

- **F5 / 断线**：**SSE buffer 续流**（同 `react_request_id` 拉事件）。
- **停止 / 中断后换一轮说话**：**`react_agent_runs` 检查点续作**（`resume_run_id`，见 session 文档 §5.2.2）。
- `agent_tasks`：工具级审计与 DAG；**不能**单独替代上述两层。
- **中断续作 + 并发**：`react_agent_runs.checkpoint.agent_task_dag` 为 DAG **快照**（见 session 文档 §5.2.4）；**精确续跑 pending 层** 需在 `run_dag_async` / 调度器侧单独立项，不能假定仅拼 prompt 即可恢复并发拓扑。

### 7.4 集成示例（需求级伪代码，非最终实现）

```text
# 原：observation = await self._execute_tool(decision)
# 新（多任务时）：
ids = []
for unit in expanded_tool_units(decision):
    tid = task_manager.create_task(name=..., params=..., dependencies=..., session_id=...)
    ids.append(tid)
    yield sse_tool_task_created(tid, ...)
await task_manager.wait_all_terminal(ids, timeout=...)
observations = task_manager.collect_results(ids)
# 再进入 observe 提示词
```

具体是否「一步一任务」或「一步多任务」由工具展开规则定义，**本文要求系统能力支持多任务 + DAG**。

---

## 8. 非功能需求

### 8.1 一致性

- 状态迁移必须满足：`pending → running → (done | failed)`，不允许非法跳变（实现层用枚举或校验函数）。

### 8.2 可用性

- 调度器异常不得导致进程崩溃：记录日志并继续下一轮扫描。
- DB 连接失败：退避重试，并打监控指标（若项目已有 Prometheus，可复用）。

### 8.3 安全

- `params`/`result` 中不得存储密钥明文；若工具返回敏感信息，需在结果写入前脱敏（与现有工具约定一致）。

### 8.4 可观测性

- 结构化日志：`task_id`、`session_id`、`name`、耗时、`status`。
- 可选：Prometheus counter/histogram（任务数、失败率、排队时长）。

---

## 9. 交付物与代码组织（实现阶段）

以下为**建议**目录，可在技术评审后调整：

| 交付物 | 说明 |
|--------|------|
| 模型 | SQLAlchemy `AgentTask`（或等价命名），Alembic/迁移脚本 |
| 服务层 | 任务 CRUD、状态机、`create_task`、`wait_terminal` 等 |
| 调度 | `TaskScheduler`：后台线程 + `ThreadPoolExecutor` + 优雅停止 |
| 集成 | `react_simplified.py` 中工具执行路径的可配置切换（串行旧路径 / DAG 新路径） |

---

## 10. 验收标准（测试要点）

1. **创建与依赖**：创建 A、B，B 依赖 A；仅 A 完成后 B 才变为 `running`。
2. **并发**：无依赖的 A、C 可同时 `running`（在池大小允许下）。
3. **失败传播**：A `failed` 时，B 按策略 A 不得执行或标记失败（与 6.1 一致）。
4. **抢占唯一性**：多线程/多轮扫描下同一任务不会出现双 `running`（压力测试或模拟并发更新）。
5. **恢复**：模拟 `running` 后杀进程，重启后任务回到可调度状态且结果一致。
6. **SSE**：前端（或集成测试）能收到任务生命周期事件且顺序合理。
7. **ReAct**：一步内多任务完成后，observe 使用的聚合结果与串行基线一致（给定相同工具输出）。

---

## 11. 风险与待定事项

| 项 | 说明 |
|----|------|
| Flask 上下文与线程 | 执行器线程必须正确绑定 `app_context` 与 session 作用域 |
| 与 SQLite 开发环境 | 若本地仍用 SQLite，需明确仅 MySQL 支持本特性或提供降级开关 |
| SSE 背压 | 高频任务事件是否需合并推送，由前端与协议评审决定 |
| 现有 `react_simplified` 复杂度 | 建议先**开关**启用 DAG 路径，默认关闭，灰度验证 |

---

## 12. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-03-26 | 初稿：依据内部提纲整理为可评审需求文档 |

---

**说明**：您提供的提纲末尾「请生成完整实现代码（models/task.py …）」属于**开发任务**；本文档仅锁定需求与验收边界，实现代码在评审通过后再按第 9、10 节拆解排期。
