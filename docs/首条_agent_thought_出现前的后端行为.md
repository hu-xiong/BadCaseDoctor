# 首条「Agent Thought」出现之前：后端做了什么

**版本**：2026-04-02  
**目的**：说明在 **步骤区 `agent_thought`** 出现前，服务端已完成的 **HTTP / gather / 上下文**；并记录 **架构优化方向**：用主循环里 **首轮 decide 的 `agent_thought`** 承接原「首轮 THINK」里的推断与规划，**省掉单独一轮 THINK 的串行耗时**。  
**主代码**：`agents/intelligent_devops_agent.py`（入口）、`agents/react_simplified.py`（`_run_stream_raw`）、`agents/react_function_call.py`（decide FC 流）。提示词中的规划约束见 `agents/prompts.py`（`think_prompt` / `[GATE]` 规则）。

---

## 1. 名词：你说的「第一个 agent thought」指哪一种

| 情形 | 含义 | 典型出现位置 |
|------|------|----------------|
| **A. 协议事件 `event: "agent_thought"`** | decide 阶段流式叙事 / FC 占位 | 每轮 `todo_start` **之后**，见 `react_simplified.py` 中 `yield {"event": "agent_thought", ...}` |
| **B. 语义对齐：`reasoning` + `as: "agent_thought"`** | 与 decide 正文同一展示语义 | 部分分支里由引擎以 `reasoning` 下发但带 `as`（与 **A** 展示一致） |

下文 **「首条 decide 上的 agent_thought」** 默认指 **A**。

---

## 2. 优化：首轮 THINK → 主循环首步 `agent_thought`（三种推断合并）

**问题**：若 **单独** 跑一轮「首轮 THINK」只做门控 + 规划说明 + Todo/XML，再 **`todo_start` → decide**，会多 **一次完整模型往返**，首条可见步骤 Thought 之前墙钟偏长，且 THINK 与首步 decide 叙事容易重复。

**目标**：**取消仅服务于规划的首轮独立 THINK**，把原先在 THINK 里要完成的内容，**合并到进入主循环后第一轮**的 **`todo_start` → decide → `agent_thought`（及同轮 FC）** 中完成，使用户更早看到 **与当前步绑定的** Thought，并少一次串行 LLM。

**不是这样做（避免理解反了）**：

- **不要**在 `todo_start` / 主循环 decide **之前**再跑一层「语义门控 LLM + 启发式拼 todos + skill 直接生成列表」当唯一真相来源——那是 **前置步骤**，与本文档目标相反。  
- **允许**的仍是现有 **gather**（库表名、工具表、pending 摘要）以及 **仅作上下文** 的 prefer_modify / skill_match（写进首轮 decide 的 `result_context` 或附加说明），**不**应用它们在主循环外「先判死纯聊、先定稿 Todo 再进主循环」。

**正确落点**：**语义门控（need_tools 等）、是否需要 Todo 列表、具体 Todo 条目、以及下面对齐的三段推断**，一律在 **主循环内** 同一次 **decide** 产出：先流式 **`agent_thought`**（自然语言里完成推断与说明），再通过 **FC（如扩展后的 submit / plan 工具）或同段 XML** 结构化落地；必要时 skill 只作为 **prompt 约束或后续步**，不顶替这轮叙事。

**「三种推断」**（与 `prompts.py` 中规划说明要求对齐，原在首轮 THINK 流里书写；**合并后写在首轮 decide 的 `agent_thought` 正文**）：

| 序号 | 推断内容 | 含义 |
|------|----------|------|
| 1 | **目标与约束** | 用户要什么、边界条件、数据范围与禁止项 |
| 2 | **路径与步骤** | 准备调用哪些工具、顺序如何，**逐步对应后续 Todo 条目 / 工具调用**（含「先 grep 再 modify」等） |
| 3 | **风险与备选** | 不确定点、失败时的备选路径 |

**分流字段**（原嵌在 `[GATE]{…}[/GATE]` 或 FC 参数里；**合并后主循环首轮 decide 的同一次调用内**判完，不必固定单独 THINK 步，也**不必**主循环外前置门控）：

- **`need_tools`**：是否走项目内工具链；`false` 则纯聊收束，不进 ACT 主循环。  
- **`need_todo_list`**：是否生成可见 `<todo_list>` / JSON 计划；`false` 时可 **无列表直驱** decide/执行。  
- **`need_plan_ui`**（可选）：有 Todo 时是否在侧栏强调规划备忘。

合并后，**首步 `agent_thought` 的正文**应能同时承载：**分流结论（或等价结构化输出）+ 上述三段推断**；再由 **FC / XML** 落地 Todo 与工具选择，避免「THINK 写一遍、decide 再写一遍」的浪费。

> **说明**：仓库内具体是否仍保留独立 `STEP 1: THINK`，以 `react_simplified.py` 当前分支为准；本节描述的是 **合并后的目标形态与产品语义**，便于对齐提示词与协议演进。

---

## 3. 从 HTTP 进入到 `_run_stream_raw` 之前

1. **SSE 连接建立**，`IntelligentDevOpsAgent.handle_user_request_stream` 先 **`yield {'type': 'hello', 'payload': {}}`**，表示协议握手就绪。  
2. **并行**启动 **`_classify_intent(user_input)`**（意图分类），**不阻塞**后续 ReAct 流；主流程立刻进入 `react_engine.run_stream`。  
3. **`run_stream`** 对 `_run_stream_raw` 吐出的字典做 **v1 打包**（`engine_dict_to_wire_packets`），并在 **`react_phase` 变化** 时插入 **`type: phase`**（若开启 `sse_v1_emit_phase_packets`）。

此阶段 **尚无** `event: agent_thought`。

---

## 4. `_run_stream_raw` 开头：gather 与上下文

在进入 **ACT 主循环**（`todo_start` → decide）之前，引擎会先：

1. **重置会话态**：locale、`project_id` / `plan_id`、pending diff 索引、工具意图合并开关（`REACT_TOOLS_INTENT_MERGE_INTO_THINK`）等。  
2. **并行 gather**（`asyncio.gather` + `asyncio.to_thread`）：  
   - **`_sync_load_project_plan_names`**：项目名 / 计划名（带短 TTL 缓存）；  
   - **`format_tools_for_prompt(self.tools)`**：工具表格式化（可截断、可缓存）；  
   - **`_relevant_pending_for_llm`**：与本次相关的 pending diff 摘要。  
3. **与 gather 同时已启动**：**`_prefer_modify_over_create(user_input)`**（改优于建仲裁）。  
4. **长期记忆**：默认用请求带入的 **`long_memory_prefetch`**；仅当 `REACT_LONG_MEMORY_QUERY_EACH_MESSAGE=1` 时才会在本条消息里再检索注入。  
5. **写 `result_context`**：`project_id`、名称、`pending_diff_summary` 等，供后续提示词使用。

---

## 5. 进入主循环到「首条 `event: agent_thought`」

合并形态下：**纯聊 vs 需工具、是否展示/生成 Todo 列表**，应在 **首轮 decide** 的结构化输出中收口（例如 FC 返回 `need_tools: false` 则本段对话直接结束，**不**依赖主循环前单独一次门控 LLM）。

当 **已进入 ACT 主循环**（`todo_start` 已发出；若首轮 Todo 来自占位/同步占位，仍以 **本轮 `agent_thought` + FC** 定稿计划与首工具）：

1. **`while` 每轮**：同步计划 SSE、`todo_start`、`step_status`（见 `round_idx == 0` 为第一步）。  
2. **构建 decide 提示词**：`decide_prompt_react_dynamic`（用户输入、工具表、缩略上下文、上一步 observation 等）。  
3. **首条 `event: "agent_thought"`** 通常出现在 **decide** 分支：  
   - **整包 FC**（`chat_completion_with_tools`）且 **`REACT_DECIDE_FC_INSTANT_HINT=1`（默认）**：在 `await` 整包结果前，先 **`yield` 一条本地化占位文案** 到 `agent_thought`，避免 Thought 区空白过久。  
   - **流式 FC**：以模型 **真实 delta** 为主逐段 `agent_thought`；占位可关。  
   - **非 FC 的 XML/叙事流**：`_stream_react_decide` 等路径边收边推 `agent_thought` delta。

在 **未合并** 的旧时序下，典型路径为：**`hello` → 首轮 THINK / 规划就绪 → 第一轮 `todo_start` → decide**。在 **§2 合并** 落地后，首条协议上的 `agent_thought` 可更早与 **三段推断** 对齐，而少一次独立 THINK。

---

## 6. 环境变量与排障速查

| 变量 | 与「首条 agent_thought 前」的关系 |
|------|-----------------------------------|
| `REACT_MERGE_FIRST_THINK_INTO_DECIDE` | **1**：跳过独立首轮 THINK；第 0 步 decide 仅用 `submit_react_think` FC 定稿门控 + todos + 可选 `first_tool`（须 `REACT_DECIDE_FUNCTION_CALL=1`）。**默认 0** |
| `REACT_TOOLS_INTENT_MERGE_INTO_THINK` | 门控是否与规划合并（默认 1）；与 §2 目标一致时可进一步收敛为「仅主循环首步」 |
| `REACT_DECIDE_FC_INSTANT_HINT` | 整包 FC 时 decide 前是否先推一条 `agent_thought` 占位 |
| `REACT_DECIDE_FC_STREAM` | decide 是否走流式 FC（边收边 `agent_thought`） |
| `PERF_LOG=1` | 打印 `[PERF][react]`、`[PERF][round-bridge]` 等分段耗时 |

---

## 7. 与现有文档的关系

历史时序、占位 step、`plan_init` 抑制等见：`docs/需求文档_首轮思考前置链路与时序_20260329.md`。  
若 §2 合并全面落地，该文档中与「独立首轮 THINK」相关的段落需按实现同步修订。
