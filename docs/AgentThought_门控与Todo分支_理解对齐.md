# Agent Thought 门控与 Todo 分支 — 理解对齐

> 第四节为**已定案**（按产品确认）；前三节为设计背景。

---

## 一、目标（产品行为）

1. **Thought 阶段分流**：闲聊直回 | 要工具且简单 → **不生成 Todo**，直接工具决策 | 要工具且复杂 → **生成 Todo** 再执行。
2. **反对**：靠「隐藏规划备忘」假装没生成 Todo；核心是**是否生成 Todo** 这一层，不是仅 UI 开关。

---

## 二、此前实现易混淆点


| 目标         | 易做错                              |
| ---------- | -------------------------------- |
| 简单不生成 Todo | 仍解析出步骤再 suppress                 |
| 门控语义       | 把 `need_plan_ui` 与「要不要 Todo」混为一谈 |


---

## 三、概念字段

- `**need_tools`**：是否走工具链。  
- `**need_todo_list**`（与 `need_plan_ui` 独立）：是否必须在 THINK 中写出 `<todo_list>`/JSON 计划；`false` 时主循环以 `todos=[]` 进入，由 decide/FC 驱动。  
- `**need_plan_ui**`：在有 Todo 时是否强调侧栏展示（可选）。

---

## 四、已定案（实现依据）

### 1. 谁决定 `need_todo_list`？

- **以模型在 `[GATE]` 里的输出为准**；服务端启发式**仅兜底**。  
- 模型输出 `need_todo_list=false` → 不生成 Todo。  
- 模型未输出或解析失败 → 启发式（如多步/多工具线索则倾向生成计划）。

### 2. 「约三步」边界

- **不设硬性数字**；由模型按任务内在复杂度判断。  
- 提示词强调：当你认为需要**分步骤**才能完成时，设 `need_todo_list=true` 并生成 Todo。

### 3. 技能（Skill）匹配成功时

- **仍生成可见 Todo**（工作流步骤），增强透明度。  
- 极轻量单步可无 Todo（未来可由 Skill 元数据定义）；当前：**有步骤则展示**，首轮无 Todo 时从工作流补全。

### 4. 流式 Thought

- `need_todo_list=false` 时，门控后说明**不进 `todos_stream`**。  
- 协议：引擎仍发 `event: reasoning`（与现有打包器一致），**payload 带 `as: agent_thought`**；前端 `reactSseV1ToStepEvent` 转为 `**agent_thought**`，并在 `applyReactThinkSSEStepEvent` 中写入 `**agentThoughtDraft` + `thinkReasoningDraft` / `reasoningContent**`，避免与「计划区」混淆。

### 5. 模型违规

- 声明 `need_todo_list=false` 仍输出 `<todo_list>`：**丢弃 Todo**，**日志告警**，**不中断**。

### 6. 工具描述与 decide 延迟

- **渐进式披露（可选）**：`REACT_TOOLS_PROMPT_INDEX=1` 时短索引 + 元工具 `**get_tool_description`**。  
- **流式 tool_calls（已落地）**：`REACT_DECIDE_FC_STREAM=1`（默认）且 LLM 实现 `**chat_completion_with_tools_stream`**（百炼 OpenAI 兼容、千帆 v2 SSE）时，decide 步边收 delta 边 `**agent_thought**`，整包失败回退 `**chat_completion_with_tools**`。关闭：`REACT_DECIDE_FC_STREAM=0`。

---

## 五、实现映射（代码）

- `[GATE]`：`agents/intent_guards.py`（`resolve_need_todo_list_effective` 等）。  
- 首轮无计划流式：`agents/react_simplified.py`（`as: agent_thought` + `index: 0`）。  
- SSE v1：`agents/sse_react_v1.py`（`_pack_stream_think` 透传 `as`）。  
- 前端：`electron-vue3/src/composables/reactSseV1ToStepEvent.js`、`applyReactThinkSSEStepEvent.js`。  
- 元工具：`agents/tools/get_tool_description_tool.py`，在 `intelligent_devops_agent._register_tools` 末尾注册。  
- 环境变量：`REACT_NEED_TODO_LIST_HEURISTIC`、`REACT_TOOLS_PROMPT_INDEX`、`REACT_TOOL_INDEX_DESC_CHARS`、`REACT_DECIDE_FC_STREAM`。

