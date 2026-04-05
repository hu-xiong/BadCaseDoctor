# 需求文档：Grep 与 Modify 候选集对齐（现状与优化方向）

## 1. 背景与问题表象

在「先 Grep 定位、再 Modify 批量改」的闭环里，用户期望：

- 左侧列表 **高亮 / 可跳转** 几条，批量 Modify 就改 **同样几条**；
- 日志里「预览 N 条」与界面「定位 N 条」一致。

实际曾出现：**Grep 展示/导航 2 条，Modify 预览 3 条**（或其它 N≠M）。这容易被理解为「Bug」，但本质是 **多套「候选集」口径并存且历史上未强制统一**。

---

## 2. 结论：是 Bug 还是工具问题？

**两者都有，更准确地说是「产品口径 + 工具链分层」问题：**

| 层面 | 说明 |
|------|------|
| **数据/业务规则** | 前端「可跳转导航」依赖 `plan_id` 等字段；无 `plan_id` 的记录可以出现在 Grep 的 `bug_location` 里，但 **不会进入 navigation**，造成「全量命中」与「可点条数」天然可能不一致。 |
| **工具（grep_tool）** | 同时产出 **`bug_location`（分析全量）** 与 **`navigation`（可跳转子集）**；两套列表职责不同，若下游只认其中一套就会偏。 |
| **编排（react_simplified）** | `result_context` 里 `bug_list` 等字段可能来自 **grep merge**、**重试**、**模型决策**、**其它 context 更新**；任一路径若未与 `navigation_ids` 对齐，就会出现批量 Modify 条数漂移。 |

因此：**不是单一字段写错就能解释**，而是需要在需求上明确 **「以哪一套 ID 为权威」**，并在全链路贯彻。

---

## 3. 当前实现：三套概念（必须区分）

### 3.1 `bug_location` / `badcase_analysis` / `testcase_location`（Grep 分析结果）

- **来源**：`grep_tool` 对计划树与关键词的检索与分析。
- **语义**：「语义上相关的记录集合」，条数可能多于用户最终在列表里点的条目。

### 3.2 `navigation` / `navigation_ids`（前端可跳转「官方候选」）

- **来源**：`grep_tool._build_grep_navigation_items` 基于上述列表生成；**仅包含有 `plan_id` 的项**（无 `plan_id` 则 `append_*` 直接跳过，不进入导航）。
- **合并**：`react_simplified._merge_grep_observation_into_context` 从 `navigation` 解析出 `grep_result.navigation_ids`（按 `bug` / `badcase` / `testcase` 分类），并用 `_restrict_by_nav` 把写入 `result_context` 的 `bug_list` 等与 **导航 ID 集合** 对齐。
- **语义**：「与用户界面跳转、高亮一致的候选 ID」。

### 3.3 Modify 的 `target_list` / `target_ids`（实际修改对象）

- **来源**：主循环里根据用户意图从 `result_context['bug_list']` 等选取；批量时为列表全体或子集。
- **语义**：「本轮 Modify 工具真实要改的 ID」；应与 **3.2** 一致，否则用户感知为「对不齐」。

---

## 4. 已落地的对齐手段（代码现状）

### 4.1 Merge 阶段（`_merge_grep_observation_into_context`）

- 若 grep 返回了 `navigation`，则按 `navigation_ids` **收窄** `bug_list` / `badcase_list` / `testcase_list` 写入 context。
- 若存在 `navigation` 但解析不到任何 id，设计上倾向于 **不退回全量列表**（避免误选），具体以当前实现为准。

### 4.2 批量 Modify 二次保险（`_constrain_modify_target_list_by_grep_navigation`）

- 当 `grep_result.navigation_ids` 对应类型 **非空** 时，批量 Modify 的 `target_list` **再与导航 ID 求交**，避免仅依赖可能被其它步骤污染的 `bug_list` 长度。

### 4.3 前端（`ProjectDetail` 等）

- 批量 pending diff 落库曾用串行 `await` 导致 UI 多次刷新；已改为并行 `Promise.all` 等优化，减轻「整块区域闪多次」的观感（与 ID 对齐是不同维度的问题）。

### 4.4 日志追踪（已实现）

- **`[GREP-NAV]`**（`_merge_grep_observation_into_context`）：grep 成功合并后输出各类 `navigation_ids`、条数、`raw_location_counts`；若存在 `navigation` 但解析后 id 全空、或某类「raw 条数 > 可导航条数」则打 **WARNING**（常见于缺 `plan_id`）。
- **`[MODIFY-TRACE]`**（同上 merge 末尾）：输出写入 context 后的 **`merge_after_ids`**（按 bug/badcase/testcase）；若某类 **merge 后 id 集合** 与 **`navigation_ids` 不一致** 则 **WARNING**。
- **`[MODIFY-TRACE]`**（`_constrain_modify_target_list_by_grep_navigation`）：批量且 `len>1` 时输出 **`merge_after_ids` / `final_target_ids` / `nav_authoritative_ids`**，`phase` 为 `main_loop` | `retry` | `planning`；若 **`navigation_ids` 为空** 则 **WARNING**（回退不收紧）；若 **与导航求交为空** 则 **ERROR**（保持原列表并需排查）；若发生收窄则 **WARNING**，否则 **`(aligned)`**。

---

## 5. 仍可能出现的边界情况（供你闭环优化时对照）

1. **无 `plan_id` 的 Bug**  
   - 会出现在 `bug_location`，但 **不会进 navigation**；merge 后 context 里该类型可能变少或为空，与用户「明明搜到了」的心理模型冲突。  
   - **产品选择**：要么要求数据侧补全 `plan_id`，要么单独定义「无计划 Bug」的导航策略。

2. **未走 grep merge 的路径**  
   - 例如缓存 grep、失败重试、技能分支、或 context 被后续步骤覆盖；若只依赖 merge 而不在 **Modify 执行前** 统一过滤，仍可能短暂不一致。

3. **`navigation` 解析失败或与数据结构演进不同步**  
   - `navigation` 的 `type` / `items` 与解析逻辑不一致时，`navigation_ids` 可能为空，此时 **约束函数不会收紧** `target_list`，可能退回到较「宽」的列表。

4. **用户意图与类型推断**  
   - `mod_target`（bug / badcase / testcase）若与用户说的不一致，会对齐到 **另一张表** 的 `navigation_ids`，表现为「改的不是我以为的那类实体」。

5. **历史数据缺失 `plan_id`**  
   - 若大量记录无 `plan_id`，建议数据清洗脚本批量补充，或在 grep 时明确提示用户「部分记录无法跳转，但仍可修改」。

6. **并发/异步干扰**  
   - 若 grep 后 context 被后续其他任务覆盖，可能造成导航集与最终 modify 集短暂不同步；当前主要通过二次约束降低概率。

---

## 6. 建议的「闭环」需求口径（可写进 PRD）

### 6.1 权威源定义

在「Grep 成功后紧跟的 Modify」场景下，以 **`grep_result.navigation_ids[目标类型]`** 为批量修改的 **唯一权威 ID 集合**（当该集合 **非空** 时）。

空集时按产品约定的 **回退策略** 执行（见 6.2）。

### 6.2 回退策略（需产品确认）

| 选项 | 说明 |
|------|------|
| **A** | 禁止修改，前端提示「所选记录无法跳转，请检查 plan_id」。 |
| **B** | 允许修改但不提供导航，UI 明确提示「部分记录无法跳转，仍可修改」。 |
| **C** | 自动补全 `plan_id`（需数据侧支持，或引导用户先创建计划）。 |

### 6.3 观测与验收

**日志（建议口径）：**

- **`[GREP-NAV]`**：输出 `navigation_ids` 及类型、数量（grep 成功时）。
- **`[MODIFY-TRACE]`**：输出 **merge 后候选 ID**（`merge_after_ids`）与 **最终 target_ids**（经二次约束后的 `final_target_ids`），可逐条对比。

若出现数量不一致，日志中应有明确的 **warning** 或 **error** 级别信息。

**UI 验收用例（产品验收标准）：**

| 用例 | 预期 |
|------|------|
| **用例 1** | Grep 定位 2 条有 `plan_id` 的记录，Modify 预览与高亮条数均为 2。 |
| **用例 2** | Grep 命中 3 条记录，其中 1 条无 `plan_id`，导航高亮 2 条，Modify 预览与导航一致为 2 条（按产品回退策略）。 |
| **用例 3** | Grep 返回空 `navigation_ids`，Modify 按回退策略处理，日志有明确警告，UI 按回退策略展示提示。 |
| **用例 4** | Grep 后因数据质量问题导致 `navigation_ids` 与 `bug_list` 不一致，最终 `target_ids` 应与 `navigation_ids` 对齐（在权威源非空时）。 |

### 6.4 数据质量要求

- 需要前端可跳转的记录 **必须有 `plan_id`**（或产品设计「不可跳转但仍可改」的独立流程，并明确 UI 表现）。
- 对历史数据，建议通过 **数据脚本批量补全** 缺失的 `plan_id`，或在 grep 时提示用户「部分记录无计划，无法跳转，但可修改」。

### 6.5 日志追踪规范（落地 checklist）

- Grep 成功时输出 **`[GREP-NAV]`**，包含 `navigation_ids` 及对应的类型、数量。**（已在 4.4 落地）**
- Modify 批量执行前输出 **`[MODIFY-TRACE]`**，包含 `merge_after_ids`（经过 merge 后的候选）、`final_target_ids`（经过二次约束后的最终 ID）。**（已在 4.4 落地）**
- 数量或集合不一致时，须有 **warning/error** 级别日志，便于线上排查。**（已落地：merge 不一致 WARNING；批量求交为空 ERROR；nav 空 WARNING）**

---

## 7. 相关代码位置（便于改代码时跳转）

| 模块 | 路径 | 作用 |
|------|------|------|
| 导航项生成、无 plan_id 过滤 | `agents/tools/grep_tool.py` — `_build_grep_navigation_items` | 决定哪些记录进入「可跳转」 |
| Grep 结果 merge、navigation_ids | `agents/react_simplified.py` — `_merge_grep_observation_into_context` | context 与导航对齐 |
| 批量 Modify 与导航求交 | `agents/react_simplified.py` — `_constrain_modify_target_list_by_grep_navigation` | 批量执行前二次收敛 |

---

## 8. 文档版本

- **用途**：描述 **当前功能现状** 与 **不一致根因**，支撑闭环优化与 PRD 迭代。
- **维护**：若实现变更，请同步更新第 4、5、7 节。

**本次修订**：2026-04-01 — 补充回退策略（A/B/C）、验收用例、日志规范（`[GREP-NAV]` / `merge_after_ids` / `final_target_ids`）、数据质量要求、边界情况（历史 `plan_id`、并发干扰）。
