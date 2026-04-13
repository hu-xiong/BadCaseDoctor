# 统一流式 ReAct 引擎说明

本文描述 BadCaseDoctor 中 **统一 XML 流式 ReAct** 的设计：单条异步生成器流水线、事件契约、SSE v1 映射与前端对齐要点，以及常见故障对照。

## 1. 定位与目标

**统一流式引擎**指：主路径只保留一条 **异步生成器**（`agents/react_simplified.py` 中的 `_run_unified_xml_stream`）。模型按 **三段式 XML** 输出「思考 + 决策」，引擎解析后执行工具，并以 **`event` 字典** 流式向下游抛出。`run_stream` 在出口通过 `engine_dict_to_wire_packets` 转为 **SSE v1**（`type` + `payload`）；`run()` **消费同一条流** 并汇总结束态，避免「流式一套、非流式再跑一遍主循环」的双实现。

目标：

- **单一事实来源**：行为以流为准，非流式只做 drain/聚合。
- **与现有 UI 协议对齐**：事件名与字段需满足 `sse_react_v1.py` 与 `reactEngineLegacyStream.js` 的约定；否则会出现工具已在后端执行、界面却无步骤、无 observation、总结区空壳等现象。

## 2. 调用链与代码位置

| 层级 | 位置 | 职责 |
|------|------|------|
| 引擎核心 | `react_simplified.py` → `_run_unified_xml_stream` | gather 上下文 → 多轮：LLM 流式 → 解析 XML → 执行工具 → 更新上下文 → `done` / `error` |
| 流式出口 | `run_stream` | `async for` 消费 `_run_unified_xml_stream`，将每条 `raw` 转为 v1 包并 `yield` |
| 非流式出口 | `run()` | `async for` drain 同一生成器，汇总 `done` 等 |
| 协议打包 | `agents/sse_react_v1.py` | `engine_dict_to_wire_packets`、`map_engine_step_to_client_packets`、`_ENGINE_EVENT_TO_PACKETS` |
| 解析 | `agents/prompts.py` | `react_unified_prompt`、`parse_unified_response` |
| 前端还原 | `electron-vue3/src/composables/reactEngineLegacyStream.js` 等 | 将 legacy `stepEvent` 写入 `aiMessage.steps`、`allObservations`、`agentResult` |

## 3. 单轮循环逻辑顺序

对每一轮 `round_idx`（上限由 `REACT_MAX_ROUNDS` 控制，默认 20）：

1. **上下文（首轮前）**  
   并行拉取项目/计划名称、工具描述、`pending_diff` 摘要等，写入 `result_ctx`，供统一 prompt 使用。若 **gather 失败**，下发 **`error` + `done(status=error)`** 后结束（与 §11 强制收口一致），不再抛未处理异常中断 SSE。

2. **`todo_start`**  
   驱动「规划备忘」扩行与当前步 `running`。前端扩行条件（`reactEngineLegacyStream.js`）为：  
   **`todo_skip !== true` 且 `expand_plan !== false` 且 `planned !== false` 且 `index >= steps.length`**。  
   统一流默认发送 **`planned: true`、`expand_plan: true`、`todo_skip: false`** 与非空 `todo` 文案。若某轮**不要**插入规划备忘行，可显式设 **`todo_skip: true`** 或 **`expand_plan: false`**（优于仅靠 `planned` 表达「隐式」语义）。

3. **LLM 流式**  
   `_stream_llm_text` 下边收边 `yield` `agent_thought`（`delta`），最后拼接完整字符串。SSE meta 上 **`agent_thought` 使用 `react_phase=think`**，以便前端把增量写入 Thought 草稿并揭示规划备忘（旧版标成 `observe_decide` 会导致统一流「只有总结、中间空白」）。

4. **解析**  
   `parse_unified_response` 得到 `decision`（`execute`、`tool`、`params`、`reason` 等）。若不再执行工具，发 **`done`**（宜带 `summary`）并结束。

5. **`executing`（建议必发）**  
   在真正执行工具前下发，字段与 `_pack_tool_start` 一致：`tool`、`index`、`step_id`、`params`、`reason`、`message` 等，便于前端显示「正在执行」与参数摘要。

6. **工具执行（含 `run_tool_with_progress` 约定）**  
   非 `modify`：``await _execute_tool``，返回后 **立即** 对 `_drain_tool_task_sse_buffer_list()` 逐条 `yield`（DAG 事件）。  
   **`modify`（且未开启 `REACT_AGENT_TASK_DAG`）**：使用 **`_spawn_modify_executor_future` + `_iter_modify_side_events_while_task`**，在 `asyncio.wait_for` 进行期间轮询 **`progress_queue`**，将进度行转为 `batch_preview_row` / `executing` 并交错下发；结束后再取 Future 结果。  
   **`modify` + DAG=1**：仍走 **`_execute_tool`**，**不**在引擎内轮询进度（与持久化包装一致）；此时中间预览可能仍只在服务端日志出现，属已知取舍。  
   进度前缀见 `modify_tool.MODIFY_BATCH_ROW_PREFIX`。

7. **工具返回之后**  
   - 失败时先发 **`tool_error`**（`stream` + `lane=tool_error` → 前端 `event: tool_error`），再发 **`observation`**（`data` 内仍带 `success: false`），便于单独订阅错误 UI。  
   - 发 **`observation`**：须与 `_pack_tool_end` 对齐，至少包含 **`tool`、`index`、`step_id`、`data`、`summary_nl`**。  
   - **`modify`（非 DAG）**：等待期间 drain；**Future 完成后**再 **drain 一次**，避免 `tool_task_done` 等晚到包丢失。**非 modify** 在 `await` 后 drain。

8. **可选 `modify_preview`**  
   若仍单独下发结构化预览，需与前端消费路径一致；批量 diff 常见路径为 **`batch_preview_row`**。

9. **更新 `result_ctx`**  
   **`grep` 成功**：必须调用 **`_merge_grep_observation_into_context`**（与旧主循环一致），从 `observation.data` 抽出 `bug_location` 等并写入 **`grep_result` / `bug_list`** 及 navigation 裁剪结果；不可仅依赖 observation 顶层字段（locate 模式结果多在 `data` 内）。其它工具仍可按顶层键合并。

10. **循环结束条件**  
    例如 `modify` 成功且进入预览/待确认后 `break`；否则进入下一轮。

11. **最终 `done`（强制收口）**  
    正常结束、``except`` 与 **`finally`** 均保证至少一次 **`done`**（异常时 `status: "error"`）。可能先出现 **`error`** 事件，再出现 **`done`**；`run()` **不会**在仅收到 `error` 时提前 `break`，以 `done` 为最终聚合点。  
    **`findings`**：每步工具一条人类可读摘要（如 `grep：…`），用于列表/要点。  
    **`summary`**：通常与 `findings` 多行拼接一致，供 `agentResult.summaryText` 与统一总结区；纯对话结束（不跑工具）时可用模型 `thinking` 填充。二者职责：**findings = 结构化要点列表，summary = 面向用户的整段正文（可等于 findings 拼接）**。

## 4. 引擎事件与 SSE v1 映射（摘要）

`map_engine_step_to_client_packets` 对常见事件的映射关系：

| 引擎 `event` | 客户端形态（概念） |
|--------------|-------------------|
| `executing` | `TOOL` + `op=start` |
| `observation` | `TOOL` + `op=end`（body 来自 **`data`**，`summary_nl` 独立） |
| `batch_preview_row` | `STREAM` + **`lane=batch_preview`**（`row` / `index` / `tool`）→ 前端 `batch_preview_row` |
| `tool_error` | `STREAM` + **`lane=tool_error`**（`message` / `tool` / `code` / `details`）→ 前端 `tool_error` |
| `agent_thought` | `STREAM` + think 通道（`as=agent_thought`） |
| `done` | `BYE`（含 `findings`、`summary`、`status?`、`steps_count`、`duration` 等） |
| 映射表未收录的事件 | `STREAM` + `lane=engine` 整包透传 |

未映射事件依赖前端是否专门解析；**核心 UX 应依赖已映射的 `executing` / `observation` / `todo_start` / `done`**。

## 5. 前端契约要点（`reactEngineLegacyStream.js` / `reactSseV1ToStepEvent.js`）

- **`todo_start`**：扩行由 **`todo_skip` / `expand_plan` / `planned`** 共同决定（见 §3）。  
- **`tool_error`**：在对应步追加错误行，并将步标为 `failed`（随后 **`observation`** 若 `success: false` 会保持 `failed`）。  
- **`observation`**：依赖 **`stepEvent.data`** 与 **`tool` / `index`**；`success: false` 时步骤为 **failed**。  
- **`done`**：`payload.status === 'error'` 时 `agentResult.status = 'error'`。`findings` 为空时会尝试从 **`allObservations`** 推导展示内容。

后端字段与上述逻辑是 **硬契约**，少字段无法靠前端猜测补全。

## 5.1 `run()` 与非流式聚合

- `run()` **只消费** `_run_unified_xml_stream`，**不**复刻主循环；默认 **不**保留完整中间包。  
- 为排障与测试，可将引擎事件摘要记入 **`result["stream_events"]`**（条数上限 **`REACT_RUN_COLLECT_EVENTS_MAX`**，默认 500，最大 5000），每条为 `{ event, tool?, index?, step_id?, status?, success? }`。  
- 遇到 **`error`** 事件时 **不**提前退出，继续消费直至 **`done`**（由引擎保证 `done` 总会发出）。

## 6. 相关环境变量（节选）

| 变量 | 含义 |
|------|------|
| `REACT_MAX_ROUNDS` | 最大 ReAct 轮数 |
| `AGENT_TOOL_TIMEOUT` | `modify` 等线程池执行超时（秒） |
| `MODIFY_BATCH_PREVIEW_STREAM` | 是否通过进度队列流式推送批量预览（常见默认开启） |
| `REACT_AGENT_TASK_DAG` | 是否走任务 DAG；开启时务必 **drain 并下发** buffer 内事件 |
| `REACT_MAIN_LOOP_LOG` | 控制台轮次/决策日志（设为 `0` 可关） |
| `REACT_RUN_COLLECT_EVENTS_MAX` | `run()` 内 `stream_events` 最大条数（0 表示不收集） |

与旧版 THINK/FC/独立 observe 相关的变量在「仅统一 XML 路径」下可能不再参与主流程，以当前 `react_simplified` 分支与 `.env` 注释为准。

## 7. 排障对照表

| 现象 | 优先检查 |
|------|----------|
| 规划备忘无步骤 | `todo_start` 是否 `planned: true`（或非 `false`）、`todo` 是否有文案、`index` 是否递增 |
| 工具已执行但步骤无结束态/无输出 | 是否发送 **`executing`**；**`observation` 是否包含完整 `data`** |
| 后端有 modify 预览日志，UI 无预览行 | 是否在 **`await` 完成前** 轮询 **`progress_queue`** 并 `yield` 对应事件 |
| 仅灰色总结、正文像无数据 | **`done.findings` / `done.summary`**；`allObservations` 是否有效 |
| 开启 DAG 后偶发缺包 | 工具返回后是否 **`yield` 全部 `_drain_tool_task_sse_buffer_list()`** |

## 8. 小结

统一流式引擎 = **一条生成器 + 与 SSE v1 / 前端 legacy reducer 严格对齐的事件契约**。实现时建议将 **`todo_start` 的规划可见性、`observation.data` 的完整性、`done` 的 findings/summary、以及 `modify` 的 progress 轮询** 与「工具是否执行成功」视为同等重要的对外输出，而非可选日志。

---

*文档版本：与仓库主分支 `react_simplified._run_unified_xml_stream` / `sse_react_v1` 行为对齐；若实现变更，请同步更新本节与排障表。*
