# 页表 + 伙伴系统：Token 管理与 KV Cache 调度

> **主线目标**：把 Agent 提示词当作「可分页的虚拟地址空间」管理——**4KB 一页**，用**伙伴系统**管理**本地页帧**（hash 索引、LRU）；对可复用前缀依赖推理侧 **KV Cache 自动命中**，对可变尾部做**压缩与按需加载**，在 **$19 限次** 商业模型下把单次 grep→modify 的 **token 成本压到竞品的 1%～5% 量级**，并支撑 **P50 ≤ 3s** 的推理延迟。
>
> 本文档是 **推理侧基础设施** 设计，与 `需求文档_下一轮性能优化_推理执行分离总结与响应形态.md`（宏路径、少轮 LLM）互补：前者减少 **调用次数**（如 skip observe），本文减少 **每次调用的有效 token 与 KV 冷启动成本**（宏路径 compact VPN 见 §1.3）。与已实现的 **streaming FC 边输出边执行** 正交（§1.4）：页表主攻 prefill/TTFT，FC 主攻 decode/early execute。

---

## 0. 文档体系（阅读顺序）

| 层级 | 文档 | 关系 |
|------|------|------|
| **总纲（性能）** | `需求文档_下一轮性能优化_推理执行分离总结与响应形态.md` | 宏路径、observe 省略、端到端 3s |
| **本文** | `需求文档_页表KV_Cache与提示词压缩.md` | 单次 LLM 调用的 token/KV 成本 |
| **路由** | `意图识别与grep-modify路由机制.md` | 哪些页在宏路径可省略 |
| **观测** | `需求文档_SDK与Prometheus指标采集.md` | `cache_hit_ratio`、每页 token 等 |
| **模型** | `需求文档_模型路由深化设计.md` | 小模型跑 L1、大模型仅复杂步 |
| **流式 FC（已实现）** | `agents/react_function_call.py`、`react_simplified._iter_*_fc_stream` | 边输出边执行；与页表 **正交**（§1.4） |

**不在本阶段展开**：训练侧自定义 CUDA kernel；多租户 GPU 集群调度（P2）。

---

## 1. 背景与问题

### 1.1 现状痛点

| 痛点 | 表现 | 根因 |
|------|------|------|
| **Token 贵** | 竞品按 credits 计；用户体感 $19 仅够 1～2 小时「扫代码」 | 整段 repo/长 observe 进上下文；每轮全量 prompt |
| **KV Cache 吃不满** | 同项目多轮聊天仍慢、prefill 占比高 | 前缀轻微变化导致整段 cache 失效 |
| **提示词膨胀** | `react_simplified` + tools schema + grep 结果 + ui_context | 无分层预算；工具输出未分页截断 |
| **无法核算** | 不知「改一条 Bug」花多少 token | 缺页级计量与配额 |

### 1.2 设计原则

1. **前缀稳定、后缀可变**：稳定页尽量 **只读 + 长期 KV 驻留**；每轮仅 append 少量新页。
2. **4KB 页**：逻辑配额单位（见 §2.2）；**伙伴系统**仅管应用侧本地页帧，**不**与 GPU KV block 做物理映射。
3. **压缩不损语义**：按 **page_type** 划分可压缩页与 **关键信息页**（如 `tool_param`）；后者 **禁止 L1+** 或 **仅 L0**（见 §4.2）。
4. **与产品一致**：宏路径（grep→modify）默认 **≤2 次 LLM**；页表应使 **第 2 次 VPN 仅 tail 追加 1～3 页**（前缀 canonical 不变 → 推理侧 cache 命中）。宏路径 **compact VPN** 与性能总纲「省略 observe」对齐，见 **§1.3**。

### 1.3 与性能总纲的关系（宏路径 compact VPN）

与 `需求文档_下一轮性能优化_推理执行分离总结与响应形态.md` **互补、不重复**：

| 维度 | 性能总纲 | 本文（页表） |
|------|----------|--------------|
| 优化对象 | **LLM 调用次数**（宏路径跳过 grep observe、跳过 inter-decide） | **单次调用的 token 量** + prefix cache 命中率 |
| 手段 | `frozen_macro`、`grep_snapshot`、stub observe | 分页、压缩、canonical 前缀、本地页帧 |
| 重叠点 | 宏路径 **不跑 observe LLM** → 上下文 **不应再携带 observe 页** | Builder 提供 **compact VPN 模板**，与宏路径开关联动 |

**宏路径 compact VPN（已定）**：当 `react_macro` 命中 grep→modify 且跳过 observe 时，`PromptPageTableBuilder` **不分配** observe / 历史轮次相关页，VPN 仅保留：

```text
P0 ─ P1 ─ P2 ─ grep_fact ─ user_turn
 ↑   ↑   ↑      ↑            ↑
静态前缀（可 ultra-compact）  唯一 tool_fact  当前轮输入 + ui_context_core
```

**相对全量 ReAct VPN，宏路径跳过**：

| 槽位 / 页类型 | 宏路径 | 说明 |
|---------------|--------|------|
| **P0～P2** | ✅ 保留 | 预生成静态片段；P1/P2 可用 ultra-compact 合并 |
| **P3** `project_ctx` | ❌ 跳过 | `project_id` 等并入 `user_turn` 的 `ui_context_core` |
| **P4** `session_prefix` | ❌ 跳过 | 无 observe LLM → 无需 `running_summary` 页 |
| **P5** `grep_fact` | ✅ 保留 | `grep_snapshot` 结构化 FACT（≤L1） |
| **P5 以后** | ❌ 全部跳过 | 含 `observe_nl`、`tool_fact_modify` 预览、历史 `tool_fact`/`tool_param` 等 |
| **Ptail** `user_turn` | ✅ 保留 | 含 `ui_context_core`（RAW） |

仍 **全量发送** 组装后的 compact `messages[]`（通常 **≤6 页**），前缀 `P0～P2 + grep_fact` 字节跨轮稳定 → 推理侧 Automatic Prefix Caching 命中。

**与宏执行阶段对齐**（性能总纲 §3）：

- 性能侧：`REACT_MACRO_SKIP_GREP_OBSERVE` → 不调用 observe LLM。
- 页表侧：同一请求 **不构建** P3/P4 及 **P5 以后**（observe/历史）页；`grep_fact` 占 P5 槽；`build_vpn(..., template="macro_compact")`。
- modify 参数优先来自 `frozen_macro` + `grep_snapshot`；仅当必须二次 LLM 抽参时，可在 `grep_fact` 与 `user_turn` 之间 **追加 1 页 `tool_param`**，仍不恢复 P5 后的历史页。

**回退**：宏计划失败 → 清除 compact 模板，恢复全量 ReAct VPN（含 P4、observe_nl 等）。

### 1.4 与 streaming function call 的关系（正交 + 首 token 延迟）

项目 **已实现**「边输出边执行」：decide / unified FC 走 `chat_completion_with_tools_stream`（`REACT_DECIDE_FC_STREAM`、`REACT_UNIFIED_FC_DECIDE`），并在 `REACT_UNIFIED_FC_EARLY_EXECUTE=1`（默认）时，`FcStreamAccumulator.try_build_decision()` 于 **arguments JSON 凑齐即中断收流、提前执行工具**。该优化作用在 **decode 段**（流式解析 + 早停），与页表所优化的 **prefill 段**（KV 复用、tail 压缩）**正交、可叠加**。

| 优化层 | 作用阶段 | 典型手段 | 页表是否介入 |
|--------|----------|----------|--------------|
| **streaming FC + early execute**（已实现） | **decode** | 流式 `tool_calls` delta；参数凑齐即 `break` 收流 → 跑 grep/modify | ❌ |
| **页表 + prefix cache**（本文） | **prefill** | canonical 前缀、compact VPN、Automatic Prefix Caching | ✅ |
| **宏路径 skip observe**（§1.3） | **调用次数 + prompt 页数** | 不建 P4/P5+ observe 页 | ✅ |

```text
  assemble          prefill（页表主战场）     decode（streaming FC 主战场）
 ─────────►  API  ─────────►  KV 就绪  ─────────►  首 token … tool_calls … early execute
     ↑                           ↑                              ↑
 P0～P3 预生成片段          cache 命中→跳过大部分 K/V          与 cache_hit_ratio 无关
 tail 拼接（ms 级）         未命中→与 prefill_tokens 成正比
```

#### 页表对首 token 延迟（TTFT）的影响

**TTFT**（Time To First Token）≈ `assemble_ms` + `network_ms` + **`prefill_ms`** + `first_decode_ms`。streaming FC **不改变** prefill 计算量，但 **首 token 内容**可能是 `content` delta 或 `tool_calls[].function.name` delta，取决于模型输出顺序——页表 **不干预** 这一 decode 行为。

| 因素 | 对 TTFT 的影响 | 说明 |
|------|----------------|------|
| **前缀 Automatic Prefix Caching 全命中** | **理论上显著降低** `prefill_ms` | 仅剩 tail（`grep_fact` + `user_turn` 等）需 prefill；TTFT 可接近「短 prompt 冷启动」量级 |
| **cache 部分命中 / 前缀漂移** | 中等 | `prefix_drift_pages` ↑ → 有效 prefill_tokens ↑ → TTFT ↑ |
| **compact VPN（§1.3）** | 降低 tail prefill | 宏路径页数少 → 即使 cache miss，prefill 仍短于全量 ReAct |
| **P0～P3 预生成片段** | 略降 `assemble_ms` | 通常 **远小于** prefill；不是 TTFT 主因 |
| **streaming FC / early execute** | **不直接改变 TTFT** | 缩短 **首 token → 工具开始执行** 的路径（decode 早停） |

**理论下界（待实测验证）**：同 session 第 2 轮 grep→modify、前缀 byte 一致且推理侧 cache 全命中时，`prefill_tokens` 应接近 tail 规模（宏路径 often **≤1K**）；TTFT **有望**降至数百 ms 量级（仍受 GPU 调度、batch、网络 RTT 约束）。**不能仅凭 cache_hit_ratio 推导 TTFT**，须与引擎侧 prefix cache 统计交叉验证。

#### 观测与实测（P0 必做 benchmark）

在现有 `bdc_llm_time_to_first_token_seconds` / agent trace 上 **按轮次关联**页表字段：

```json
{
  "span": "prompt.pages",
  "data": {
    "cache_hit_ratio": 0.92,
    "prefill_tokens": 850,
    "ttft_ms": null,
    "early_execute_ms": null,
    "tool_start_ms": null
  }
}
```

| 指标 | 来源 | 用途 |
|------|------|------|
| `ttft_ms` | LLM 插件 / `[PERF]` | 与 `cache_hit_ratio` 分桶对比（冷/温/热前缀） |
| `prefill_tokens` | 页表 Postflight | 解释 TTFT 变化主因 |
| `early_execute_ms` | unified FC early break 时间点 − 请求发出 | decode 段优化效果；**与页表无关** |
| `tool_start_ms` | 工具入口 − 请求发出 | 端到端「开始干活」感知 |

**基准用例（须实测，见 §9.2）**：

1. **Round 1**（冷前缀）：streaming FC 开，记录 TTFT + prefill_tokens。
2. **Round 2**（同 session、canonical 前缀不变）：期望 `cache_hit_ratio ≥ 0.8` 且 **TTFT 相对 Round 1 显著下降**；若未下降 → 查 `prefix_drift_pages` 或引擎 APC 是否生效。
3. **宏路径 compact VPN**：在 Round 2 上对比全量 ReAct VPN 的 TTFT 与 prefill_tokens。

> **结论（设计态）**：页表通过 **减少 prefill 工作量** 影响 TTFT；streaming FC 通过 **压缩 decode 等待** 影响 tool 启动时间。两者叠加才是 grep→modify **P50 ≤ 3s** 的完整路径，但 **TTFT 与 cache 命中的定量关系必须以 Round1/2 A/B 实测为准**，本文档不写死 ms 承诺。

---

## 2. 核心概念：提示词页表（Prompt Page Table）

### 2.1 虚拟地址空间

把一次 LLM 请求的 `messages[]` 线性化后，按 **固定大小页** 切分：

```
┌─────────────────────────────────────────────────────────────┐
│  VPN（Virtual Prompt Namespace）per session / per request   │
├────────┬────────┬────────┬────────┬────────┬──────────────┤
│ P0     │ P1     │ P2     │ P3     │ ...    │ Pn（可变尾） │
│ system │ tools  │ project│ session│ ...    │ user+obs     │
│ 4KB    │ 4KB    │ 4KB    │ 4KB    │        │ 4KB          │
└────────┴────────┴────────┴────────┴────────┴──────────────┘
         ↑ 常驻 / 高 cache 命中              ↑ 每轮更新
```

**页表项（PTE）建议字段**：

| 字段 | 说明 |
|------|------|
| `page_id` | 全局唯一（session_id + 逻辑页号） |
| `vpn_slot` | 逻辑页索引（P0…Pn） |
| `content_hash` | 页内容 BLAKE3/xxHash；用于 KV 复用 |
| `token_count` | 该页实际 token 数（≤ 页上限） |
| `flags` | `RO` 只读 / `PIN` 常驻 / `COMPRESSED` / `EVICTED` |
| `kv_handle` | （可选）推理侧 PagedAttention block id，**仅观测/trace**；buddy **不**持有、**不**要求与本地页帧连续 |
| `last_used_at` | LRU |
| `ref_count` | 多请求共享前缀时引用计数 |

### 2.2 4KB 页与 token 换算

LLM 无字节页概念，**4KB 为逻辑配额单位**：

| 模型族 | 建议 `tokens_per_page` | 说明 |
|--------|------------------------|------|
| 中文为主 Qwen/DeepSeek | **800～1000 tokens/页** | 约 4KB UTF-8 中文 |
| 英文为主 | **1200～1500 tokens/页** | 可配置 |

**配置项（环境变量）**：

```bash
BADCASE_PROMPT_PAGE_BYTES=4096
BADCASE_PROMPT_TOKENS_PER_PAGE=900   # 默认按模型校准
BADCASE_PROMPT_MAX_PAGES=128         # 单请求 VPN 上限 ≈ 115K tokens
```

实现层：`page_byte_budget` 用于 **存储与传输**（压缩后落盘）；`page_token_budget` 用于 **API 计费与 KV 分配**。

### 2.3 逻辑页类型（固定顺序）

| 槽位 | 类型 | 典型内容 | 复用性 |
|------|------|----------|--------|
| **P0** | `system_core` | 角色、安全、语言 | 全局 PIN |
| **P1** | `tools_schema` | 工具名 + 参数 schema 摘要（非全文） | 按工具集版本 PIN |
| **P2** | `workflow_rules` | grep/modify 宏规则、雪花 ID 约束 | 按 locale + 版本 PIN |
| **P3** | `project_ctx` | project_id、计划树摘要（非全量） | 按 project 版本 |
| **P4** | `session_prefix` | 本会话已确认步骤摘要（`running_summary` 压缩版） | 按 session 增量 append |
| **P5…Pk-1** | `tool_fact` | grep 命中 FACT、modify 预览结构化 diff | 每步 1～2 页 |
| **Pk** | `tool_param` | decide/modify **待填参数**、字段 key、目标 `record_id` | 每步 0～1 页 |
| **Ptail** | `user_turn` | 当前 user_input + `ui_context` 最小集 | 每轮刷新 |

**与现有代码对齐**：

- `locale_prompts.py` 的 FACT 前缀（`本步事实：modify.target=…`）→ 独立 **tool_fact 页**，避免与自然语言 observe 混页。
- decide/modify 工具调用的 **参数字段块** → 独立 **`tool_param` 页**（关键信息页，见 §4.2），与 observe 摘要分离。
- `react_macro` 宏路径 → **P1/P2 可合并为 ultra-compact 页**；VPN 用 **`macro_compact` 模板**（§1.3）：仅 `P0～P2 + grep_fact + user_turn`。

---

## 3. 伙伴系统（Buddy Allocator）——本地页帧管理

> **职责边界（已定）**：伙伴系统 **仅** 用于 **应用进程内** 的本地页帧管理——VPN 槽位分配/回收、`content_hash` 索引、LRU 淘汰、页元数据存储。  
> **不要求** 与推理侧 KV block **物理连续**，也 **不做** 1:1 映射或 KV block 调度；prefix 复用由推理侧 Automatic Prefix Caching 独立完成。

### 3.1 为什么用伙伴系统

- 页大小为 **2 的幂次方倍数**（1 页、2 页、4 页…）便于 **合并/分裂** 本地空闲页帧。
- 提示词段长度不一（tools schema 可能 6KB、grep 结果 12KB）→ 在 **逻辑 VPN** 上分配 **2^n 页** 连续槽位，减少本地页表外部碎片。
- 同一 `content_hash` 可 **多 VPN 共享** 同一本地页帧（去重 + 引用计数），支撑命中率 trace 与 LRU 回收。
- **与 KV block 无关**：vLLM/SGLang 自行管理 GPU block 池；应用侧 buddy 不介入 prefill/decode 调度。

### 3.2 数据结构（示意）

```text
BuddyAllocator（应用进程内，非 GPU 页帧）
├── free_lists[0..MAX_ORDER]   # 2^i 本地页帧槽的空闲链
├── page_frames[M]             # 本地页帧：content、content_hash、flags、last_used_at、ref_count
├── hash_index[content_hash]   # content_hash → page_frame_id（去重、命中率统计）
└── vpn_table[session_id]      # 逻辑 VPN → page_frame_id 列表（VPN 槽连续，页帧 **不要求** 物理连续）

allocate(n_pages) -> vpn_range   # 分配 VPN 槽位，O(log n) 分裂
free(vpn_range)    -> 合并伙伴，回收到 free list
evict_lru()        # 淘汰非 PIN 冷页，释放 **本地** 页帧；不驱逐推理侧 KV block
```

**PIN 页**：不参与 LRU 淘汰（P0～P3）；**EVICT** 仅针对 `session_prefix` 与 `tool_fact` 冷页。

### 3.3 与 KV Cache 引擎对接

> **API 约束（已定）**：OpenAI-compatible Chat Completions **必须发送完整 `messages[]`**，不支持「只传 NEED_PREFILL 页 / 增量前缀块」。  
> 因此**放弃**「应用层仅发送未命中页」方案；改为 **全量 messages 发送 + 前缀字节串跨请求完全一致**，由推理侧 **Automatic Prefix Caching**（如 vLLM APC、SGLang radix cache）在 prefill 时自动复用已缓存 block。

| 步骤 | 行为 |
|------|------|
| **Assemble（应用层）** | 每轮输出**完整 canonical `messages[]`**；稳定前缀页（P0～Pn）**字节级不变**，仅 tail append 新页 |
| **Prefill（推理侧）** | 引擎按 token block 比对 prefix；命中 → **跳过该段 K/V 计算**；未命中 → 计算并写入 block pool |
| **Decode** | 仅对最后一页（user_turn）增量；历史页 KV 只读 |
| **请求结束** | 递减本地 `ref_count`；PIN 页永驻；非 PIN 冷页经 buddy **LRU 回收本地页帧**（推理侧 KV 由引擎自行 LRU） |

**应用层 canonical 规则**（保证 prefix 可命中）：

- 固定字段顺序、JSON minify、统一换行符；禁止「同义不同串」（如随机 UUID 进 system、时间戳进静态页）。
- 页表 `content_hash` 用于**监控 prefix 漂移**与 trace；**不**用于裁剪 API payload。

**Assemble 性能**（避免每轮全量序列化）：

- **P0～P3 静态前缀**：进程启动或版本 bump 时 **预生成 canonical `messages` 片段**（bytes / 已序列化 JSON 块），按 `(locale, tools_version, project_id)` 缓存；每轮 **零拷贝引用**，不重新 `json.dumps` 整段前缀。
- **P4～Ptail 动态尾**：每轮仅对 `session_prefix`、`tool_fact`、`user_turn` **增量序列化**，再与前缀片段 **拼接** 成完整 `messages[]`。
- 页表 VPN 仍为内部视图；对外 API payload = `static_prefix_blob + dynamic_tail_blob`（逻辑全量发送，物理避免重复序列化）。

**目标指标**：

| 场景 | prefix cache 命中率 | 说明 |
|------|---------------------|------|
| 同 session 第 2 轮 modify | **≥ 85%** | P0～P4 + grep FACT 命中 |
| 同 project 换 session | **≥ 60%** | P0～P3 命中 |
| 冷启动 | 0% | 首次加载 PIN 页 |

---

## 4. 提示词压缩（按页策略）

压缩发生在 **写入页之前**；解压仅推理引擎内部需要，不对用户展示。

### 4.1 压缩分级

| 级别 | 手段 | 典型压缩比 | 适用 page_type |
|------|------|------------|----------------|
| **RAW** | 不压缩 | 1× | `ui_context_core`（`target`/`record_id`/`view` 等） |
| **L0 无损** | 去空白、JSON minify、去重复 bullet | 1.1～1.3× | `system_core`、`tools_schema`、`workflow_rules`、`tool_param`、`tool_fact_modify` |
| **L1 结构化** | 表格化；禁 snippet 全文 | 3～10× | `tool_fact_grep` |
| **L2 摘要** | 规则/小模型 → FACT 一行 | 5～20× | 长 `observe_nl` |
| **L3 语义摘要** | 仅保留 `running_summary` Confirmed 段 | 10×+ | `session_prefix` |

### 4.2 关键信息页（压缩上限，**硬编码**）

> **风险**：L1+ 压缩 `tool_param` 等页会丢字段名/ID → modify 参数幻觉。  
> `PageCompressor` **必须先读 `page_type`**，不得对下表类型应用超过「最高级别」的压缩；Preflight 缩 tail 时 **跳过** 关键信息页。

| page_type | 典型内容 | 最高级别 | 说明 |
|-----------|----------|----------|------|
| **`tool_param`** | modify/decide 参数、字段 key、`record_id`、`plan_id` | **L0**（推荐 **RAW**） | 一步一参；禁止表格化/摘要 |
| **`tools_schema`** | P1 工具名 + 参数 schema | **L0** | 禁止省略 optional/required 字段 |
| **`workflow_rules`** | P2 宏规则、雪花 ID 约束 | **L0** | 禁止语义改写 |
| **`ui_context_core`** | `user_turn` 内 ID/view 子块 | **RAW** | 字节级不变 |
| **`tool_fact_modify`** | modify `before/after` 结构化 diff | **L0** | 禁止合并/截断 diff 行 |

**可激进压缩（非关键）**：`tool_fact_grep`（≤L1）、`session_prefix`（≤L3）、`observe_nl`（≤L2）。

**实现约束**：`PromptPage.compression_max` 由 `page_type` 查表赋值；若 `level > compression_max` → **拒绝压缩** 并 trace 告警 `compression_blocked`。

### 4.3 禁止进页的内容

- 整段 `react_simplified` 源码级说明（改为 **P2 索引表**：「详见宏路径 B1-B4」）。
- 重复 `success=true`、工具名中英双语套话。
- 未截断的 ES hit JSON、modify `before/after` 全量（预览走 **`tool_fact_modify` 页**，≤1 页，§4.2）

### 4.4 ui_context 最小化

| 字段 | 是否进页 | 说明 |
|------|----------|------|
| `target`, `record_id`, `view` | ✅ **`ui_context_core`** | 雪花 ID；**RAW**，见 §4.2 |
| `title` | ✅ 单行 | 与总结页 `record_title` 一致 |
| `plan_id` | ✅ | |
| 全量表单字段 | ❌ | 按需 grep |

---

## 5. Token 管理与商业配额

### 5.1 三级预算

```text
Account（$19/月）
 └── SessionBudget（软限 token / 硬限 request）
      └── RequestBudget（单轮 prefill + decode 上限）
           └── PageBudget（每页 token 上限 + 总页数上限）
```

| 档位 | 月 token 软限 | 单轮 prefill 上限 | 说明 |
|------|---------------|-------------------|------|
| **Starter $19** | 例如 8M tokens | 24 页（≈21K） | 日常 grep/modify |
| **Pro** | 更高 | 48 页 | browser/vision 另计 |
| **Enterprise** | 合同 | 自定义 | 私有化 PIN 页本地驻留 |

**重任务单独计量**：vision 截图、全库深扫按 **页类型 `vision_*`** 扣减，不走 Starter 无限口径。

### 5.2 调度策略

1. **Preflight**：组装 VPN 前估算 token；超预算 → 先 **压缩非关键 tail**（`session_prefix` L2→L3、`observe_nl` L2；**跳过** `tool_param` 等关键页），仍超 → 拒绝或降级小模型。
2. **Postflight**：写入 `observability/agent_trace`：`prefill_tokens`, `decode_tokens`, `cache_hit_pages`, `evicted_pages`。
3. **与 macro 联动**（§1.3）：宏路径跳过 observe → compact VPN **`P0～P2 + grep_fact + user_turn`**，**不分配 P5 以后**（含 P4 `session_prefix`、P3 独立页）；仍全量发送组装结果（通常 ≤6 页）；前缀 `P0～P2 + grep_fact` 字节不变以命中 cache。

---

## 6. 系统架构

```mermaid
flowchart TB
  subgraph app [BadCaseDoctor Python]
    React[react_simplified / macro]
    PT[PromptPageTableBuilder]
    BA[BuddyAllocator 本地页帧]
    CM[PageCompressor]
  end
  subgraph infer [推理服务 vLLM / 自研]
    PC[PrefixCache Automatic]
    PA[PagedAttention KV blocks]
    SCH[BatchScheduler]
  end
  React --> PT
  PT --> CM
  CM --> BA
  CM -->|canonical messages[]| SCH
  BA -.->|hash 索引 / LRU / PTE trace| PT
  SCH --> PC
  PC --> PA
```

### 6.1 模块职责

| 模块 | 语言 | 职责 |
|------|------|------|
| `PromptPageTableBuilder` | Python | 从 messages/tools/ui_context 生成 VPN |
| `PageCompressor` | Python | L0～L3 压缩；**按 `page_type` 硬编码 `compression_max`**；关键信息页禁 L1+ |
| `CanonicalMessagesAssembler` | Python | P0～P3 预生成片段缓存 + P4～Ptail 增量拼接 → 完整 `messages[]` |
| `BuddyAllocator` | Python（先）→ Go（后） | **本地页帧**：VPN 槽位、`content_hash` 索引、LRU 淘汰；**不**调度 KV block |
| `PrefixCacheServer` | 推理侧 | Automatic Prefix Caching（block 级 prefix 匹配，非应用层 hash 索引） |
| `TokenMeter` | Python | 配额扣减、trace 输出 |

### 6.2 请求生命周期（单轮）

1. **Build**：`build_vpn(session, request)` → List[Page]
2. **Compress**：每页 `compress(page, level=auto)`；**关键信息页**（§4.2）不得超过 `compression_max`
3. **Allocate**：`buddy.alloc(len_pages)` → vpn_range
4. **Resolve KV（观测用）**：对每个 PTE 算 `content_hash`；与上轮 VPN 比对 → 标记 `CACHE_HIT` / `PREFIX_DRIFT` / `NEW_PAGE`（**仅 trace/告警，不裁剪 payload**）
5. **Assemble API**：取 **预生成 P0～P3 片段** + **本轮序列化 P4～Ptail** → 拼接为完整 canonical `messages[]`；前缀字节与上轮一致 → 推理侧 Automatic Prefix Caching 自动跳过重复 prefill
6. **Record**：`append_agent_trace(span="prompt.pages", data={..., cache_hit_pages, prefix_drift_pages})`

---

## 7. 与现有 BadCaseDoctor 组件的集成点

| 现有位置 | 集成方式 |
|----------|----------|
| `agents/react_simplified.py` `_stream_unified` | decide/observe 前调用 `build_vpn`；宏路径 `template="macro_compact"`（§1.3） |
| `agents/locale_prompts.py` | 系统 prompt 拆为 P0/P1/P2 静态页；**启动时预生成 messages 片段**；版本号 bump 时整页换 hash 并刷新缓存 |
| `agents/react_macro.py` | 宏执行跳过 observe → Builder **不建 P4/P5+ 页**；仅 `P0～P2 + grep_fact + user_turn` |
| `agents/react_function_call.py` | streaming FC / early execute **不变**；页表仅缩短其上游 `messages[]` prefill（§1.4） |
| `utils/observability.py` | 新增 span：`prompt.pages`, `kv.cache_hit`, `token.budget`；**关联** `ttft_ms` / `early_execute_ms`（§1.4） |
| `routers/agent.py` | 请求入口 `TokenMeter.preflight(user_id, session_id)` |
| `config.py` | 页大小、配额；`CRITICAL_PAGE_TYPES` / `compression_max` 注册表 |

---

## 8. 数据结构（Python 草案）

```python
@dataclass
class PromptPage:
    slot: int
    page_type: str          # system_core | tool_param | tool_fact_grep | ...
    content: str
    content_hash: str
    token_count: int
    flags: int              # PIN | RO | COMPRESSED | CRITICAL
    compression_level: int  # 实际应用级别 0-3；RAW 记为 0 且 flags 无 COMPRESSED
    compression_max: int    # 由 page_type 查 §4.2 表；PageCompressor 硬上限

@dataclass
class PromptVPN:
    session_id: str
    request_id: str
    pages: list[PromptPage]
    buddy_order: int        # 2^order 页数
    total_tokens: int

class BuddyAllocator:
    def alloc(self, n_pages: int) -> tuple[int, int]: ...  # start_slot, order
    def free(self, start_slot: int, order: int) -> None: ...
```

**存储（可选 P1）**：`session_id` → 最近 VPN 序列化到 Redis，断线重连恢复 PIN + session_prefix 页 hash。

---

## 9. 观测与验收

### 9.1 Trace 字段（扩展现有 JSONL）

```json
{
  "span": "prompt.pages",
  "data": {
    "total_pages": 12,
    "prefill_pages": 3,
    "cache_hit_pages": 9,
    "prefix_drift_pages": 0,
    "cache_hit_ratio": 0.75,
    "prefill_tokens": 2100,
    "decode_tokens": 180,
    "ttft_ms": 420,
    "early_execute_ms": 680,
    "tool_start_ms": 690,
    "fc_stream": true,
    "buddy_order": 4,
    "compression_saved_tokens": 8400
  }
}
```

### 9.2 基准用例（与性能总纲一致）

| 用例 | 验收 |
|------|------|
| grep → modify 改 Bug 状态 | 第 2 次 LLM **cache_hit_ratio ≥ 0.8**；prefill_tokens **≤ 3K** |
| 同上 + **streaming FC 开**（默认） | Round2 **TTFT 相对 Round1 显著下降**（须实测记录，不写死 ms；见 §1.4） |
| 宏路径 compact VPN + Round2 | `prefill_tokens` **≤ Round2 全量 ReAct**；TTFT 趋势与 prefill_tokens 一致 |
| 同 session 连续 5 次 modify | 总 token **线性增长**，非指数 |
| $19 账户模拟 100 次 modify | 总 token **≤ 月软限 90%** |

### 9.3 Prometheus（可选）

- `badcase_prompt_prefill_tokens_total`
- `badcase_kv_cache_hit_ratio`
- `badcase_prompt_pages_evicted_total`
- `badcase_prompt_ttft_by_cache_hit`（Histogram：按 `cache_hit_ratio` 分桶的 TTFT，**P1 实测后启用**）

---

## 10. 实施路线

| 阶段 | 内容 | 产出 | 优先级 |
|------|------|------|--------|
| **P0** | 逻辑分页 + token 计量 + trace；L0/L1 压缩；**P0～P3 静态 messages 片段预生成**；**Round1/2 TTFT×cache_hit 基准采集** | 可见 cache_hit；TTFT 关联数据（不测不承诺 ms） | **必做** |
| **P1** | BuddyAllocator + canonical messages builder；对接 vLLM Automatic Prefix Caching | 命中率 ≥ 85%（同 session，全量发送前提下） | **必做** |
| **P2** | Token 配额与 $19 档位；vision/browser 独立页类型 | 商业闭环 | 应做 |
| **P3** | 推理侧 block 调度优化（与 buddy **正交**）；Go 化本地页帧分配器 | 极致成本 | 可选 |

**建议目录（实现时）**：

```text
memory/prompt_page_table.py
memory/buddy_allocator.py        # 本地页帧：VPN 槽位、hash_index、LRU（非 KV block 调度）
memory/page_compressor.py        # 按 page_type 压缩上限；CRITICAL 页禁 L1+
memory/canonical_messages.py   # P0～P3 预生成片段 + P4～Ptail 拼接；content_hash / prefix_drift 监控
utils/token_meter.py
tests/test_buddy_allocator.py
tests/test_prompt_page_table.py
```

---

## 11. 风险与边界

| 风险 | 缓解 |
|------|------|
| **过度压缩导致 modify 参数错** | **已定**：关键信息页类型（`tool_param`、`ui_context_core` 等）**禁止 L1+** 或 **仅 L0/RAW**；`PageCompressor` 按 `page_type` 硬编码 `compression_max` |
| hash 碰撞 | 128-bit hash + 碰撞时 force prefill |
| **前缀字节漂移导致 cache 全失效** | canonical builder；静态页 PIN；`content_hash` 监控 `prefix_drift_pages` |
| API 不支持部分发送 | **已定**：全量 `messages[]` + 服务端 Automatic Prefix Caching；页表仅内部视图与计量 |
| **页表与 messages 转换开销** | **P0～P3 预生成 canonical 片段**（版本 bump 时刷新）；**P4～Ptail 每轮单独序列化后拼接**；避免每轮对整个 VPN 做 `json.dumps` |
| 页表与 messages API 语义对齐 | Builder 维护 VPN 内部视图；对外仍输出完整 `messages[]`（前缀引用 + 尾拼接） |
| **伙伴系统作用模糊** | **已定**：buddy **仅**本地页帧（VPN 槽位、`content_hash` 索引、LRU 淘汰）；**不要求**与 KV block 物理连续或 1:1 映射 |
| **与现有性能优化重叠** | **互补**：性能总纲减 **调用次数**（skip observe）；页表减 **单次 token**；宏路径共用 **`macro_compact` VPN**（§1.3），不重复建 observe 页 |
| **streaming FC 与页表职责混淆** | **正交**（§1.4）：FC 优化 decode/early execute；页表优化 prefill/KV；TTFT 与 cache 命中 **须实测**，不写死 ms |

---

## 12. 一句话总结

> **把 Agent 提示词按 4KB 逻辑页分页，用伙伴系统管本地页帧（`content_hash` 索引、LRU）；静态前缀 PIN 住且 canonical 序列化保证字节一致，动态尾部压缩成 FACT 页；每次 LLM 调用全量发送 `messages[]`，由推理侧 Automatic Prefix Caching 跳过重复 prefill，在同 session 下把 cache 命中率推到 85%+，从根上兑现「$19 敞开用日常改单」的成本结构。**

---

## 13. 关联文档

- `需求文档_下一轮性能优化_推理执行分离总结与响应形态.md`
- `需求文档_模型路由深化设计.md`
- `需求文档_SDK与Prometheus指标采集.md`
- `意图识别与grep-modify路由机制.md`
