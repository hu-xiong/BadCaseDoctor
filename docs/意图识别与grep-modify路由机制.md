# 意图识别与 Grep / Modify 路由机制

> **性能优化关联**：宏路径 `frozen_macro` 的**规则触发**应与本文字段/实体路由一致；总纲见 [推理/执行分离](./需求文档_下一轮性能优化_推理执行分离总结与响应形态.md) §3.3。

本文描述当前代码里**「用户想改什么实体」**如何被识别，以及 **grep**、**modify** 在 ReAct 主循环中如何配合；并给出一套可演进的**分层决策机制**，用于处理 Bug / Card / BadCase / TestCase 等口径并存时的模糊输入。

> 与「候选条数、导航 ID、批量 modify 对齐」相关的专项说明见：  
> [`需求文档_grep与modify候选集对齐_现状与优化方向.md`](./需求文档_grep与modify候选集对齐_现状与优化方向.md)（本文不重复展开 navigation 与 `bug_list` 收窄细节）。

---

## 1. 为什么要单独谈「模糊」

系统里同时存在：

| 概念 | 典型主键 | 典型可改字段 |
|------|-----------|--------------|
| **源表行** | `Bug.id`、`BadCase.id`、`TestCase.id` | `status`、`severity`、`steps_to_reproduce`、`title` 等 |
| **迭代卡片 Card** | `Card.id` | `title`、`description`、`plan_id` 等；**与源表部分字段镜像不同步**（例如 `title` 可独立于 `Bug.title`） |

因此会出现两类经典歧义：

1. **主键撞号**：同一项目下 `Bug.id` 与 `Card.id` 可能数值相同，若仅凭数字推断「是 Bug 还是卡片」会错表。  
2. **字段同名**：`title`、`description` 在 Card 与源表上都可能存在，但**业务含义**不同（看板展示名 vs 缺陷库标题）。

「意图识别」的目标是在调用工具前，尽量稳定地得到：`(实体类型, 主键, 可选 card_id)`，而不是把「列表上那一行」默认等价成某一种表。

---

## 2. 意图识别：当前分层（谁在什么时候判断）

### 2.1 第一层：用户话术中的**显式实体类型**（`agents/intent_guards.py`）

在合并 `user_input` 与 `todo` 的文本上，用规则函数判断是否**明确**指向某一类实体（优先级由调用方决定，例如 `_infer_modify_target_explicit` 中 **testcase > card > plan > badcase > bug**）：

| 函数 | 作用（摘要） |
|------|----------------|
| `user_text_implies_bug_entity_type` | 中文含「**缺陷**」或英文整词 `bug` / `bugs` |
| `user_text_implies_card_entity_type` | 「**卡片** / card」与标题、描述、名称、重命名、`card_id` 等组合；或「**看板**」与标题/名称/重命名；或「修改…卡片」类短句 |
| `user_text_implies_plan_entity_type` | 「迭代计划」「计划树」「搜计划」等 |
| `infer_modify_target_from_user` | 从单段 `user_input` 粗猜 grep/modify 的 target（测例 / 坏例 / card / plan / bug / **all**） |

**特点**：规则可解释、无模型成本；对「口语省略主语」仍可能返回 `None` 或 `all`，交给下层。

### 2.2 第二层：ReAct 主循环对 **modify 参数的 enrich**（`agents/react_simplified.py`）

`execute` 前会走 `_enrich_modify_decision_for_main_loop`，核心逻辑包括：

1. **显式类型优先**：若 `_infer_modify_target_explicit` 命中，则 `target` 以用户话术为准。  
2. **仅一种列表有数据时的粗分类**：例如只有 `testcase_list` → `testcase`；只有 `bug_list` → `bug` 等。  
3. **仅命中卡片列表（`card_list`）时**：  
   - 若 `user_text_implies_card_entity_type` 为真 → **固定 `target=card`**，并从卡片行写入 `card_id`（避免「想改看板标题却被抬到 bug」）。  
   - 否则若存在 `grep_modify_raw_bug_list` 等原始列表 → 历史上为防 **status 误走 card**，会把 `target` **抬到** `bug` / `badcase` / `testcase`。  
   - 再否则用 `_modify_target_from_card_grep_row` 根据行的 `source_type` / `source_id` / `type` 反推源表 `target` + `target_id`，并可附带 `card_id`。  
4. **`_last_grep_target == 'card'` 时的分支**：与上类似，并增加 `_card_intent` 对「卡片层意图」的同样门禁。  
5. **补全 `target_id` / `card_id` / `target_ids`**：与 `grep_result`、`merged list`、导航约束等配合（详见对齐文档）。  
6. **探索与提取 modifications**：在缺 `modifications` 时可能 `explore_record` + LLM/正则提取字段。  
7. **主决策**（`resolve_modify_target_and_id`）：在 enrich 末尾根据 `modifications` + `ModifyResolutionContext` 统一校正 `target` / `target_id` / `card_id`。
   - 当已是 `target=bug`、本次 modifications **仅有 `title`**、上一轮 grep 为 **card**、且话术中**没有**「缺陷标题 / bug标题」等源表标题语义时，根据卡片行里的 `source_id` 与 Bug id 对齐，将本次 modify **改回 `target=card` + `card_id`**，使看板上的 `Card.title` 可被单独更新（与 `modify_tool` 中「title 不自动镜像」的数据语义一致）。

**`_modify_params_ready`**：除 `target_id` / `target_ids` / `natural_query` 外，**`target=card` 且已有 `card_id`** 也视为可执行 modify（避免纯卡片改标题被误判缺参）。

### 2.3 第三层：**modify_tool 内**的校正与执行（`agents/tools/modify_tool.py`）

工具层再次收敛「最终写哪张表」，主要机制包括：

1. **`card_id` 与 `Card.source_type`**：若传入 `card_id`，可用 `_normalize_target_using_card_row` 将 LLM 误选的 `target` 校正为源表类型，并把仍等于 `Card.id` 的 `target_id` 换成**源表主键**。  
2. **主键撞号消解**：若未传 `card_id`，仅 `target_id` 在 Card 表也存在同号行，**且**已声明 `bug`/`badcase`/`testcase` 且该源表行存在 → **不**把本次调用强行解释为「改 Card」（避免误改卡片）。  
3. **`target=card` + 源表工作流字段**：由 **`resolve_modify_target_and_id`** 在参数进入 `modify_tool` 前将 target 校正为源表（与旧 `_coerce_card_modify_to_source_when_applicable` 等价目标）。  
4. **字段映射与沙箱**：`_get_original_data` 按最终 `target` 选择 ORM 路径（进度文案如「正在查询 Bug 记录」与真实 `target` 一致）。  
5. **工具描述（给模型的 system 口径）**：强调 **「先看 modifications 字段属于哪张源表」**，grep 的 `target=card` 仅表示检索面，不表示 modify 一定用 `card`。

---

## 3. Grep：当前怎么处理「搜什么」

- **target 参数**：可限定 `bug` / `badcase` / `testcase` / `card` / `plan` / `all` 等；主循环里可能通过 `_widen_grep_target_to_include_cards_unless_explicit` 在未显式限定源表时放宽为含 Card，避免列表数据在 Card 层却搜不到。  
- **产出**：除各类型列表外，还有 **navigation** 与原始命中列表（如 `grep_modify_raw_*`）供后续 modify enrich 使用。  
- **与 modify 的关系**：grep 负责**扩大/收窄候选**；**最终改哪张表**由 modify 的 `target` + 工具内校正 + 上文 enrich 共同决定，**grep 的 target 不必与 modify 的 target 相同**。

---

## 4. Modify：当前怎么处理「改什么」

可概括为三条优先级（与工具内注释一致）：

1. **字段归属优先**：`status`、`steps_to_reproduce`、`severity` 等明显属于缺陷工作流的字段 → **应落在 Bug（或对应源表）**，即使 grep 只在 Card 上命中。  
2. **卡片展示层**：用户明确要改「卡片 / 看板」上的标题、描述，且本次修改字段仅落在 Card 可写列 → **`target=card` + `card_id`（或 card 主键）**。  
3. **主键与关联**：通过 `card_id`、`source_type`/`source_id`、`Bug.card_id` 等把 ID 对齐，避免「以为在改 Bug 其实在改 Card」或相反。

---

## 5. 建议的「流程机制」——统一处理模糊输入（可落地为产品 + 协议）

下面是一套**与具体 UI 解耦、可测试**的决策管线，便于后续把规则从散落代码收拢到单一策略模块（或小型状态机）。

### 5.1 输入信号（Signals）

在每次即将调用 **grep** 或 **modify** 前，收集结构化信号，而非仅依赖一句自然语言：

| 信号 | 来源示例 |
|------|-----------|
| `S_explicit_entity` | `intent_guards` 显式 bug/card/plan/… |
| `S_last_grep_target` | `result_context._last_grep_target` |
| `S_mod_fields` | `modifications` 的 key 集合（映射后） |
| `S_has_raw_bug_list` | `grep_modify_raw_bug_list` 非空 |
| `S_card_row` | 当前选中/最佳匹配的 card 行 dict（含 `source_type`、`source_id`、`type`、`id`） |
| `S_nav_ids` | navigation 权威 ID（与对齐文档一致） |
| `S_user_editing_surface` | 可选：前端上报「当前焦点在计划树 / 缺陷详情 / 看板列标题」 |

### 5.2 决策阶段（Stages）

**阶段 A — 是否必须先定位**

- 无 `target_id`/`card_id` 且无可靠 `natural_query` → 先 **grep**（或走 `plan_id` 约束的 locate）。

**阶段 B — 实体类型（Entity resolution）**

1. 若 `S_explicit_entity` 非空 → **采用**（最高优先级）。  
2. 否则若 `S_mod_fields` 含 **仅源表字段**（如 `status`）→ **源表类型**由 `S_card_row.source_type` 或字段→类型映射表确定。  
3. 否则若 `S_mod_fields` 仅为 `{title}`：  
   - 若 `S_explicit_entity` 或话术命中 **卡片层** → **Card**；  
   - 若话术命中 **缺陷源表标题** → **Bug**（或对应源表）；  
   - 若 `S_last_grep_target == card` 且无源表标题语义 → 默认 **Card**（与当前「title 回头路由」一致）。  
4. 否则在「仅 card 列表 + raw_bug 列表」冲突时：用 **卡片层意图** 门禁决定是否仍抬到源表（当前由 `_card_intent` 实现）。

**阶段 C — 主键解析（ID resolution）**

- 在确定实体类型后，再解析主键；**禁止**在类型未定前用「数字是否存在于 Card」单独决定类型（撞号场景）。  
- 若类型为源表且存在 `card_id`，仍可同时带上 `card_id` 供镜像或 UI 回跳。

**阶段 D — 执行与可观测性**

- 日志与 SSE 进度中同时打印 **`entity` + `table_pk` + `optional_card_id`**，避免只写「正在查询…」而看不出真实表。

### 5.3 与 UI 的契约（减少模糊）

- **跳转 grep 结果**：文案上区分「跳转到卡片（Card #id）」与「跳转到缺陷（Bug #id）」；若一行数据同时有两类 id，协议里可同时下发。  
- **从列表发起「改标题」**：由前端带上 `editing_surface: card_title | bug_title` 或等价枚举，作为 `S_user_editing_surface`，优先级可高于弱话术。

### 5.4 演进建议

| 方向 | 说明 |
|------|------|
| **策略集中** | 将 enrich 内分散分支收拢为「Signals → Decision」纯函数或小型类，便于单测与回归。 |
| **显式协议字段** | 在 agent 与前端之间增加可选字段 `modify_surface` / `entity_hint`，仅在模糊场景使用。 |
| **数据一致策略** | 产品层面约定：改 Bug 标题时是否同步 Card.title；若需要双写，应在 modify_tool 或服务层**显式双写**，而非依赖隐式镜像。 |

---

## 6. 相关代码入口（维护时查阅）

| 模块 | 入口/符号 |
|------|------------|
| **字段层解析（无 LLM）** | `agents/intent/resolution.py`：`FIELD_TO_TABLE`、`ModifyResolutionContext`、`resolve_modify_target_and_id`、`infer_source_tuple_from_card_dict`；包入口 `agents/intent/__init__.py` |
| 显式意图 | `agents/intent_guards.py`：`user_text_implies_*`、`infer_modify_target_from_user` |
| Modify enrich | `agents/react_simplified.py`：`_enrich_modify_decision_for_main_loop`（末尾 `resolve_modify_target_and_id`）、`_modify_target_from_card_grep_row`（委托 `infer_source_tuple_from_card_dict`）、`_modify_params_ready` |
| Grep 放宽 | `agents/react_simplified.py`：`_widen_grep_target_to_include_cards_unless_explicit` |
| Modify 执行与校正 | `agents/tools/modify_tool.py`：`execute`、`_modify_source_row_exists`、`resolve_modify_target_and_id`（撞号与 remap 后）、`_resolve_linked_source_row_for_card_modify`、`_get_original_data` |
| 候选与导航对齐 | 见 [`需求文档_grep与modify候选集对齐_现状与优化方向.md`](./需求文档_grep与modify候选集对齐_现状与优化方向.md) |

---

## 7. 文档版本说明

- 本文描述的是编写时主分支上的**行为级**机制；具体条件分支以代码为准。  
- 若后续调整 enrich 或 `intent_guards`，请同步更新本文 **§2、§5** 中的表格与阶段说明。
