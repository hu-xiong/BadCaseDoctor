# 工具导航闭环：modify / create / delete / grep 与 Tab、面包屑、Diff 展示

本文约定 **ReAct 工具（grep、modify、create、delete）** 从对话区跳转到工作台主区时的**闭环行为**：何时复用 Tab、如何遵守 **迭代计划 → 卡片 → Bug / BadCase / TestCase** 的层级、Tab 标题与面包屑如何命名，以及 **Diff 在列表与详情中的落点**。实现上以 `electron-vue3/src/components/ProjectDetail.vue`、`SimpleChatPanel.vue` 为准，后端工具仅负责产出 `navigation` / `modifyNavigation` 等可被前端消费的字段。

---

## 1. 目标读者与范围

- **读者**：前端实现、联调、产品与测试验收。
- **范围**：grep 定位、modify 沙箱/待确认、create 新建预览、delete 预览在 **同一项目工作台** 内的导航与展示闭环。
- **不在本文**：意图识别与 enrich 细节（见 [`意图识别与grep-modify路由机制.md`](./意图识别与grep-modify路由机制.md)）；grep 与 modify 候选集对齐（见 [`需求文档_grep与modify候选集对齐_现状与优化方向.md`](./需求文档_grep与modify候选集对齐_现状与优化方向.md)）。

---

## 2. 层级结构（不可跨越展示）

业务上的主区层级为：

```text
迭代计划（Plan）
  └── 卡片（Card，看板行）
        └── Bug / BadCase / TestCase（源表记录，挂在卡片下）
```

**约束：界面不得「跨层」冒充上一层。**

| 场景 | 禁止（反例） | 正确 |
|------|----------------|------|
| 展示 Bug/BadCase/TestCase **子类型列表** | Tab 标题用**迭代计划名**，主区却是某卡片下的 Bug 列表 | Tab 标题应为 **卡片标题**；面包屑为 **迭代计划名 / 卡片标题** |
| 仅改 **卡片**（卡片表、未进入某子类型列表） | 与子类型列表混用同一套 Tab 命名 | Tab 标题 = **迭代计划名**；面包屑仅 **迭代计划**（与 `plan-list`、`urlContentType=null` 的卡片表一致） |
| 从对话跳转 | 不展开计划树、不切 `selectedPlan`，直接假定用户在正确列表 | 应先解析 `plan_id`，**展开计划树**到目标计划，再激活对应 Tab 与列表/详情 |

---

## 3. Tab 复用与新建

### 3.1 复用规则

- 工作台 Tab 以稳定 **`id`** 区分（例如 `plan-{planId}`、`type-list-{type}-{planId}-{cardId}`）。
- **`upsertWorkbenchTab`**：若已存在同 `id` 的 Tab，则 **合并更新 meta/title 并视为复用**；否则 **push 新 Tab**。
- 导航完成后应 **`activateWorkbenchTab`** 切到目标 Tab，并把 Tab 条 **滚入可视区域**（与当前 `scrollActiveWorkbenchTabIntoView` 行为一致）。

### 3.2 何时新建、何时只激活

- **计划层列表**（卡片表或计划下统一列表视图）：`upsertAndActivatePlanListTab`，`kind: 'plan-list'`，`id: plan-{planId}`。
- **卡片下某一类型列表**（Bug / BadCase / TestCase）：`upsertAndActivateTypeListTab`，`kind: 'type-list'`，`id: type-list-{type}-{planId}-{cardId}`；标题为 **`cardTitle`（卡片标题）**，`meta` 中带 `planId`、`cardId`、`type`、`cardTitle`。
- 若 **`meta.cardTitle` 暂缺**（分页首屏未加载到该卡片），应用 **watch 从 `cards` / `filteredCards` 补全**，避免面包屑退化成「只有计划名」而被误认为层级错误。

---

## 4. Tab 标题与面包屑（产品规范）

### 4.1 类型列表 Tab（Bug / BadCase / TestCase 列表）

- **Tab 标题**：**卡片标题**（truncate 长度上限与现有 `truncateForTab` 一致）；无标题时兜底为 `{type}列表` 等，但应尽快补全为真实卡片名。
- **面包屑**（`getTypeListBreadcrumb`）：**`{迭代计划名称}/{卡片标题}`**。若卡片标题仍不可用，则仅显示计划名（实现上避免「计划名/空段」造成误读）。

### 4.2 计划列表 Tab（卡片表 / 改卡片）

- **Tab 标题**：**迭代计划名称**（来自计划树 `planObj.name`）。
- **面包屑**：与计划列表视图一致，为 **迭代计划** 语境（不强行拼接卡片段，除非 UI 明确为双层结构）。

### 4.3 与「禁止跨层」的对应关系

- **不允许**：Tab 显示计划名，内容却是「某卡片下的 Bug 列表」——用户无法从 Tab 识别当前卡片。
- **允许且推荐**：Tab = 卡片标题，面包屑第一段 = 计划、第二段 = 卡片，主区为子类型列表或详情。

---

## 5. 各工具导航闭环

### 5.1 grep

- **对话侧**：`SimpleChatPanel` 中 `handleNavigation` 对 `type === 'expand_and_locate'` 派发 **`grep-navigate`**（`CustomEvent`，`window`）。
- **detail 要点**：`planId`、`recordId` / `bugId`、`target`（`bug` / `badcase` / `testcase` / `card` 等）、可选 `card_id`；卡片层命中时 **`prefer_card_layer: true`**，避免把 Card 导航错误提升为 Bug 子列表。
- **工作台侧**：`ProjectDetail` **`handleGrepNavigate`**：解析计划、展开树、必要时 **`getCardDetail` 将 card 提升为源表类型**（非 `prefer_card_layer` 场景）、再 **`upsertAndActivatePlanListTab` / `upsertAndActivateTypeListTab`** 与高亮滚动。

### 5.2 modify（含沙箱预览与待确认）

- **对话侧**：`handleShowModifyInList` 派发 **`show-modify-in-list`**，payload 含 `target`、`target_id`、`plan_id`、`diff`、`modifications`、`messageId` 等。
- **工作台侧**：`handleShowModifyInList`：
  - 解析 `plan_id`（事件、diff 中 `plan_id` 行、当前列表、API `resolvePlanIdByRecordApi` 等多路兜底）。
  - **`target === 'card'`**：打开 **计划下卡片表**（`urlContentType=null`），**不得**因 `title` 等列表字段误开 Bug/BadCase 子 Tab。
  - **`target ∈ {bug,badcase,testcase}`**：`resolveCardRowForModifyListNav` 后 **`upsertAndActivateTypeListTab`**，保证 **计划 → 卡片 → 子列表**。
  - **仅列表字段** vs **含详情字段** 的分流见第 6 节。
- **批量 / 已采纳**：可走 `__modifyListBatch` 或再次 `grep-navigate`（如 `recordIds`、`openDetail`），与上述 Tab 规则一致。

### 5.3 create

- **对话侧**：派发 **`show-create-in-list`**（及 **`create-pending`** 等与会话 pending 协同的事件，以代码为准）。
- **工作台侧**：在对应计划/卡片上下文中打开列表或创建流，Tab 仍遵守 **第 2～4 节**；新建已落地后的「跳到已有行」可与 **grep-navigate** 复用（`navigate_to_existing` + `created_id` 路径）。

### 5.4 delete

- **对话侧**：派发 **`show-delete-in-list`**。
- **工作台侧**：`handleShowDeleteInList` 中与 modify 类似地解析计划、**优先 `upsertAndActivateTypeListTab`**（在能解析到 `cardRow` 时），否则回退计划列表 Tab；高亮与滚动与 modify 列表导航一致。

---

## 6. Diff 展示：列表字段 vs 详情字段

字段分类以 `ProjectDetail` 中 **`LIST_FIELDS`** 与 **`DETAIL_FIELDS`**（经 **`normalizeDiffFieldKey`** 归一化）为基准：

- **列表字段**（当前：`title`、`status`、`assignee`）：  
  - **优先在列表行内**展示待确认 Diff / 采纳控件（行内 ✓/✗ 等）；**不**为纯列表字段改动自动打开详情页。
- **详情字段**（长文本、步骤、描述、部分优先级等）：  
  - 在 **Bug / BadCase / TestCase 详情（主编辑器）** 中展示 Diff。
  - **展示位置**：每个字段 **上方** 展示该字段的 before/after diff（含 **下拉框、选择类字段** 的选项变更），避免 diff 与控件分离导致看不清「改的是哪一项」。

**混合修改**（同时含列表列与详情字段）：

- 列表列在 **列表** 上行内处理；
- 详情字段需用户 **打开编辑页** 或通过列表上的 **展开入口（如 ▶）** 进入详情确认；文案上应明确「标题/状态/负责人在列表采纳；其余在详情」。

**仅详情字段、无列表字段变更**：自动 **`openMainEditor`** 打开对应详情并带 diff（`suppressAutoOpenDetail` 等链路除外）。

---

## 7. 验收检查清单（建议）

- [ ] 同一 `planId` + 同一 `urlContentType` 重复 grep/modify：**不重复堆 Tab**，仅激活已有 `plan-{id}`。
- [ ] 同一 `planId` + `cardId` + `type` 重复进入子列表：**复用** `type-list-...` Tab，标题为卡片名。
- [ ] Bug 列表视图：Tab ≠ 单独计划名冒充；面包屑为 **计划/卡片**。
- [ ] 改卡片：停留在 **卡片表** Tab，标题与面包屑符合 **第 4.2 节**。
- [ ] 只改 `title`/`status`/`assignee`：**列表行内**可见 diff；不强制开详情。
- [ ] 改描述、步骤等：**详情内**、**字段上方** diff；下拉选项变更同样有 diff。

---

## 8. 实现锚点（维护用）

| 能力 | 主要位置 |
|------|-----------|
| Tab upsert / 复用 | `ProjectDetail.vue` → `upsertWorkbenchTab` |
| 计划列表 Tab | `upsertAndActivatePlanListTab`（`id: plan-{planId}`） |
| 卡片下类型列表 Tab | `upsertAndActivateTypeListTab`（`id: type-list-{type}-{planId}-{cardId}`） |
| 类型列表面包屑 | `getTypeListBreadcrumb` |
| modify 列表导航 | `handleShowModifyInList`（`show-modify-in-list`） |
| grep 导航 | `handleGrepNavigate`（`grep-navigate`）；对话侧 `SimpleChatPanel.vue` → `handleNavigation` |
| 列表 / 详情字段分流 | `LIST_FIELDS`、`DETAIL_FIELDS`、`normalizeDiffFieldKey`、`openMainEditor` |
| 卡片标题补全 | `watch(activeWorkbenchTabId, cards, filteredCards)` 内对 `type-list` 的 `meta.cardTitle` 补全 |

---

## 9. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-13 | 初稿：闭环 Tab 复用、三层结构、Tab/面包屑命名、列表与详情 Diff 规则，并与当前 `ProjectDetail` / `SimpleChatPanel` 行为对齐。 |
| 2026-05-13 | 落地：`handleOpenTypeList` 改为稳定 `type-list-{type}-{planId}-{cardId}` 与 `upsertAndActivateTypeListTab` 复用；工作台列表区混合修改提示条；`NewBug` 问题分类下拉字段上方 diff。 |
| 2026-05-13 | `handleShowModifyInList`：当修改**仅为列表字段**（`title`/`status`/`assignee`）时，若未能打开 `type-list`，**禁止** fallback `openMainEditor(show_diff)`，改为 `upsertAndActivatePlanListTab`，与 §6「纯列表字段不自动开详情」一致；批量 `__pendingSyncedBatch` 路径同样约束。`NewBadcase`：`show_diff` 下校验 `pendingModifyDiff` 的 `target`/`targetId`，避免串单污染标题。 |
| 2026-05-13 | 卡片解析：`resolveCardForListNav` 优先用 `Card.source_type`+`source_id` 命中源表 id（不再强依赖 `Card.type===badcase`）；`resolveCardRowByRecordDetailApi` 在详情无 `card_id` 时从当前 `badcases` 列表行补 `card_id`，以稳定打开 `type-list-*` Tab（卡片标题 + 面包屑）。`getBadcaseStatusText` 将 `reopen` 归一到 `reopened`；i18n 增加 `list.badcaseStatus.reopen`。 |
| 2026-05-13 | 后端：`BadCase.card_id` 为空时按 `Card.project_id`+`Card.source_id` 反查卡片并写回（列表 GET 与详情 GET），保证 API 带 `card_id`，工作台沙箱可挂 `type-list` Tab。 |
