<template>
  <div class="agent-task-run" v-if="steps && steps.length">
    <!-- 1) 待办概览：与步数无关，始终展示（便于对照下方逐步执行） -->
    <div v-if="steps.length >= 1" class="agent-plan">
      <div
        class="agent-plan-header"
        role="button"
        tabindex="0"
        :title="planExpanded ? '点击收起' : '点击展开'"
        @click="togglePlan"
        @keydown.enter.prevent="togglePlan"
        @keydown.space.prevent="togglePlan"
      >
        <div class="agent-plan-header-left">
          <img class="agent-plan-list-icon" :src="todoListIcon" alt="" />
          <span class="agent-plan-title">规划备忘</span>
        </div>
        <img
          class="agent-plan-chevron"
          :src="planExpanded ? chevronDownIcon : chevronRightIcon"
          alt=""
          :title="planExpanded ? '点击收起' : '点击展开'"
        />
      </div>
      <div v-show="planExpanded" class="agent-plan-rows">
        <div
          v-for="(s, i) in steps"
          :key="'p-' + i"
          class="agent-plan-row"
          :class="{
            'is-running': s.status === 'running',
            'is-done': s.status === 'completed',
            'is-skip': s.status === 'skipped',
            'is-err': s.status === 'error'
          }"
        >
          <span class="agent-plan-icon" aria-hidden="true">{{ planIcon(s) }}</span>
          <span class="agent-plan-num">{{ i + 1 }}.</span>
          <span class="agent-plan-text">{{ planRowShown(s, i) }}</span>
          <span v-if="s.status === 'running'" class="agent-plan-badge">进行中</span>
        </div>
      </div>
    </div>

    <!-- 2) Thought → 执行 → 决策与观察 -->
    <div class="agent-logs">
      <div
        v-for="(s, i) in steps"
        :key="'l-' + i"
        v-show="showLogBlock(s)"
        class="agent-step-outer"
      >
        <div v-if="i > 0" class="agent-step-divider agent-step-divider--between" />

        <!-- Thought：仅行动前说明（decide / agent_thought）；观察段正文不在此展示 -->
        <div v-if="hasStepThought(s)" class="agent-preface-thought">
          <div class="agent-preface-thought-inner">
            <button
              type="button"
              class="agent-preface-thought-summary"
              :aria-expanded="thoughtOpen(i)"
              @click="toggleThought(i)"
            >
              <span class="agent-preface-thought-pill">{{ stepThoughtTitle(s) }}</span>
              <span v-if="thoughtSecondsMuted(s)" class="agent-preface-thought-meta">{{ thoughtSecondsMuted(s) }}</span>
              <span class="agent-preface-thought-chevron" aria-hidden="true">{{ thoughtOpen(i) ? '▾' : '▸' }}</span>
            </button>
            <div
              v-show="
                thoughtOpen(i) &&
                (hasReasoningBody(s) || thoughtBodyFallback(s) || (s.phaseWait && s.phaseWait.active))
              "
              class="agent-preface-thought-feed"
            >
              <!-- ReAct Thought：自然语言 Markdown；后端已分轨不推送原始 XML -->
              <div
                v-if="s.phaseWait?.active"
                class="agent-phase-wait"
                role="status"
                aria-label="等待中"
              >
                <span class="agent-phase-wait-dots" aria-hidden="true">
                  <span class="agent-phase-wait-dot"></span>
                  <span class="agent-phase-wait-dot"></span>
                  <span class="agent-phase-wait-dot"></span>
                </span>
              </div>
              <div
                v-if="thoughtReasoningRaw(s).trim()"
                class="agent-thought-deep-reason agent-thought-rich reasoning-markdown agent-thought-md"
                v-html="formatThoughtMarkdown(thoughtReasoningRaw(s))"
              />
              <div
                v-if="thoughtContentRaw(s).trim()"
                class="agent-thought-deep-content agent-thought-rich reasoning-markdown agent-thought-md"
                v-html="formatThoughtMarkdown(thoughtContentRaw(s))"
              />
              <div
                v-if="!thoughtReasoningRaw(s).trim() && !thoughtContentRaw(s).trim()"
                class="agent-preface-thought-plain agent-preface-fallback"
              >{{ thoughtBodyFallback(s) }}</div>
            </div>
          </div>
        </div>

        <!-- 工具执行：每种工具单独一种卡片样式，标题即工具名 -->
        <div
          class="agent-step-card agent-tool-exec-card"
          :class="[
            'agent-tool-exec-card--' + execToolKind(s),
            { 'agent-step-card--after-thought': hasStepThought(s) }
          ]"
          :data-agent-step="i"
        >
          <div v-if="showExecBlock(s)" class="agent-tool-exec-body">
            <div class="agent-tool-exec-titlebar">
              <span class="agent-tool-exec-icon" aria-hidden="true">{{ execToolIcon(s) }}</span>
              <span class="agent-tool-exec-name">{{ toolChipShort(s) }}</span>
            </div>
            <div v-if="streamText(s)" class="agent-step-section agent-step-section--nest">
              <pre
                class="agent-step-pre agent-step-pre--stream agent-step-pre--exec"
                :class="'agent-step-pre--tool-' + execToolKind(s)"
              >{{ execStreamShown(s, i) }}</pre>
            </div>
            <div v-if="s.resultSummary" class="agent-step-exec-result">{{ s.resultSummary }}</div>
          </div>

          <div
            v-if="s.grepNavigation && s.grepNavigation.type === 'multiple' && s.grepNavigation.items?.length"
            class="agent-step-section agent-step-grep-nav"
          >
            <div class="agent-step-label">定位结果</div>
            <details class="agent-grep-nav-details" open>
              <summary class="agent-grep-nav-summary">
                <span class="agent-grep-nav-title">{{ grepNavSectionTitle(s.grepNavigation.items) }}</span>
                <span class="agent-grep-nav-count">{{ s.grepNavigation.items.length }} 条</span>
              </summary>
              <div class="agent-grep-nav-list">
                <button
                  v-for="(navItem, ni) in s.grepNavigation.items"
                  :key="ni"
                  type="button"
                  class="agent-grep-nav-item"
                  @click="emit('grep-bug-click', navItem)"
                >
                  <span class="agent-grep-nav-icon" aria-hidden="true">➤</span>
                  <span class="agent-grep-nav-item-title">{{ grepNavItemTitle(navItem) }}</span>
                  <span v-if="navItem.plan_name" class="agent-grep-nav-plan">{{ navItem.plan_name }}</span>
                </button>
              </div>
            </details>
          </div>

          <div v-if="s.stepDurationMs != null && s.stepDurationMs >= 0" class="agent-step-dur">
            耗时 <strong>{{ (s.stepDurationMs / 1000).toFixed(2) }}s</strong>
          </div>
        </div>
        <!-- /agent-step-card -->

        <!-- 决策与观察：工具执行结束后再展示；与 Planning 合并为同一标题（仅副文案提示流式观察中） -->
        <div v-if="showDecisionBlock(s)" class="agent-decision-panel">
          <div class="agent-step-phase agent-step-phase--decide">
            <div class="agent-step-phase-eyebrow agent-decide-eyebrow">
              决策与观察
              <span v-if="showObserveWaiting(s)" class="agent-step-planning-inline"> · Planning next moves</span>
            </div>
            <div v-if="hasParamsSummary(s)" class="agent-step-section agent-step-section--nest">
              <div class="agent-step-sublabel">入参说明</div>
              <pre class="agent-step-pre agent-step-pre--params agent-step-pre--stream agent-step-pre--decide">{{ paramsSummaryShown(s, i) }}</pre>
            </div>
            <div v-if="hasLlmDraft(s)" class="agent-step-section agent-step-section--nest">
              <div class="agent-step-sublabel">观察结论</div>
              <div
                v-if="String(s.llmDraft || '').trim()"
                class="agent-decision-observe-rich agent-thought-rich agent-step-pre--decide reasoning-markdown agent-thought-md"
                v-html="formatThoughtMarkdown(String(s.llmDraft || ''))"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { marked } from 'marked'
import todoListIcon from '../assets/todo-list-icon.svg'
import chevronRightIcon from '../assets/chevron-right-qoder.png'
import chevronDownIcon from '../assets/chevron-down-qoder.png'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  /** 历史会话等：计划行不要逐字动画，直接显示全文 */
  instantPlan: { type: Boolean, default: false }
})

const emit = defineEmits(['grep-bug-click'])

marked.setOptions({ gfm: true, breaks: true })

const formatThoughtMarkdown = (text) => {
  const t = String(text || '').trim()
  if (!t) return ''
  try {
    return marked.parse(t, { gfm: true, breaks: true })
  } catch {
    return ''
  }
}

const planExpanded = ref(true)

const togglePlan = () => {
  planExpanded.value = !planExpanded.value
}

const grepNavSectionTitle = (items) => {
  if (!items?.length) return '点击跳转到列表'
  const ts = [...new Set(items.map((i) => (i?.target || 'bug').toString().toLowerCase()))]
  const map = { bug: 'Bug', badcase: 'BadCase', testcase: '测试用例' }
  if (ts.length === 1) return `点击跳转到 ${map[ts[0]] || ts[0]}`
  return '点击跳转到列表'
}

const grepNavItemTitle = (navItem) => (navItem && (navItem.title || navItem.bug_title)) || ''

const planIcon = (s) => {
  if (s.status === 'completed') return '✅'
  if (s.status === 'running') return '▢'
  if (s.status === 'skipped') return '⏭'
  if (s.status === 'error') return '⚠'
  return '▢'
}

/** 本步思考：对照待办列表后再展开推理（与上方「待执行步骤」呼应） */
const thoughtPanelOpen = ref({})

/** 有步骤 running 时定时刷新，使「Thought for X.Xs」随本步耗时递增（对齐 Cursor，而非静态 Thinking…） */
const thoughtUiTick = ref(0)
let thoughtTimer = null
watch(
  () => (props.steps || []).some((s) => s.status === 'running'),
  (running) => {
    if (running) {
      if (thoughtTimer) return
      thoughtTimer = setInterval(() => {
        thoughtUiTick.value++
      }, 200)
    } else if (thoughtTimer) {
      clearInterval(thoughtTimer)
      thoughtTimer = null
    }
  },
  { immediate: true }
)

/**
 * Thought 仅展示「行动前」叙述：agent_thought + decide + 非 observe 的 reasoning_step。
 * observe 段（工具结果后的模型解读）不放入此处，避免与 grep 执行区 / 观察结论重复。
 */
const thoughtReasoningRaw = (s) => {
  const chunks = [s.agentThoughtDraft, s.reasoningDecideDraft, s.reasoningStepDraft]
    .map((x) => (x && String(x).trim()) || '')
    .filter(Boolean)
  if (chunks.length) return chunks.join('\n\n')
  const u = (s.thoughtReasoningDraft || '').trim()
  return u ? String(s.thoughtReasoningDraft) : ''
}
/** 深度思考 content 侧（一般为空：XML 不再注入此处） */
const thoughtContentRaw = (s) => String(s.thoughtContentDraft || '')

const hasReasoningBody = (s) =>
  !!(String(thoughtReasoningRaw(s)).trim() || String(thoughtContentRaw(s)).trim())

/** 短工具名，强调原子动作而非「步骤序号」 */
const toolChipShort = (s) => {
  const t = String(s.title || 'tool').toLowerCase()
  if (t.includes('grep')) return 'grep'
  if (t.includes('modify')) return 'modify'
  if (t.includes('create')) return 'create'
  if (t.includes('search')) return 'search'
  if (t.includes('database')) return 'database_query'
  return String(s.title || 'tool')
}

/** 执行卡片按工具分子类（样式与语义一致） */
const execToolKind = (s) => {
  const t = String(s.title || '').toLowerCase()
  if (t.includes('grep')) return 'grep'
  if (t.includes('modify')) return 'modify'
  if (t.includes('create')) return 'create'
  if (t.includes('search')) return 'search'
  if (t.includes('database')) return 'database'
  return 'other'
}

const execToolIcon = (s) => {
  const k = execToolKind(s)
  const map = {
    grep: '⌕',
    modify: '✎',
    create: '＋',
    search: '◉',
    database: '⚗',
    other: '◇'
  }
  return map[k] || map.other
}

/** 尚无 Agent 说明 / reasoning/content 流时占位 */
const thoughtBodyFallback = (s) => {
  if (hasReasoningBody(s)) return ''
  if (s.status === 'running') {
    return '（等待本步 Agent 行动说明流式输出…）'
  }
  return '（本步未收到 Agent 行动说明。）'
}

const stepThoughtTitle = (s) => {
  void thoughtUiTick.value
  const t = s.thoughtTiming
  if (t && t.durationMs != null) {
    const thr = t.briefThresholdMs ?? 800
    // 以累计毫秒为准（行动前叙述轨）；observe 不计入 Thought 展示
    if (t.durationMs < thr) return 'Thought briefly'
    return `Thought for ${(t.durationMs / 1000).toFixed(1)}s`
  }
  // 无后端 reasoning_timing 时：用「本步开始 → 首次 executing」近似思考时长；勿把工具执行（modify 等）算进 Thought
  if (s.stepStartedAt != null && hasReasoningBody(s)) {
    const endWall =
      s.thoughtPhaseEndAtMs != null ? s.thoughtPhaseEndAtMs : s.status === 'running' ? Date.now() : null
    if (endWall != null) {
      const sec = Math.max(0, (endWall - s.stepStartedAt) / 1000)
      if (s.status === 'running' || s.thoughtPhaseEndAtMs != null) {
        return `Thought for ${sec.toFixed(1)}s`
      }
    }
  }
  if (s.status === 'running' && hasReasoningBody(s)) return 'Thinking…'
  return 'Thought'
}

const thoughtSecondsMuted = (s) => {
  const t = s.thoughtTiming
  // 实时标题已含秒数，不再右侧重复
  if (s.status === 'running' && (!t || t.durationMs == null) && s.stepStartedAt) return ''
  if (!t || t.durationMs == null) return ''
  const thr = t.briefThresholdMs ?? 800
  if (t.durationMs < thr) return ''
  return `${(t.durationMs / 1000).toFixed(1)}s`
}

// 有可展示正文、或正在等待结构化 XML（phase_wait）时展示 Thought
const hasStepThought = (s) =>
  hasReasoningBody(s) || !!(s.phaseWait && s.phaseWait.active)

const thoughtOpen = (i) => {
  const k = String(i)
  const v = thoughtPanelOpen.value[k]
  if (v !== undefined) return v
  const s = props.steps[i]
  if (!s) return true
  if (hasReasoningBody(s)) return true
  if (s.phaseWait && s.phaseWait.active) return true
  // 仅有占位说明时默认折叠，与 Cursor「先见 Thought 条、再点开」一致
  if (thoughtBodyFallback(s)) return false
  if (!s.thoughtTiming) return true
  return false
}

const toggleThought = (i) => {
  const k = String(i)
  thoughtPanelOpen.value = { ...thoughtPanelOpen.value, [k]: !thoughtOpen(i) }
}

const planLineText = (s, i) => {
  const raw = (s.originalTodo || s.title || `备忘 ${i + 1}`).trim()
  if (raw.length > 120) return raw.slice(0, 118) + '…'
  return raw
}

/** 待执行步骤列表：逐字显示每行（instantPlan 时与 planLineText 一致） */
const planLineDisplay = ref([])
const planTargetStrings = ref([])
let rafPlan = null

const planRowShown = (s, i) => {
  if (props.instantPlan) return planLineText(s, i)
  return planLineDisplay.value[i] ?? ''
}

const runPlanTypewriter = () => {
  if (props.instantPlan) return
  const tick = () => {
    rafPlan = null
    const tg = planTargetStrings.value
    if (!tg.length) return
    let cur = [...planLineDisplay.value]
    let needMore = false
    for (let i = 0; i < tg.length; i++) {
      const target = tg[i] || ''
      const shown = cur[i] || ''
      if (shown.length < target.length) {
        const backlog = target.length - shown.length
        const n = Math.min(backlog, Math.max(1, Math.ceil(backlog / 8)))
        cur[i] = target.slice(0, shown.length + n)
        needMore = true
      }
    }
    planLineDisplay.value = cur
    if (needMore) {
      rafPlan = requestAnimationFrame(tick)
    }
  }
  if (rafPlan != null) return
  rafPlan = requestAnimationFrame(tick)
}

watch(
  () => props.steps,
  (steps) => {
    if (props.instantPlan) {
      if (rafPlan != null) {
        cancelAnimationFrame(rafPlan)
        rafPlan = null
      }
      if (!steps?.length) {
        planLineDisplay.value = []
        planTargetStrings.value = []
        return
      }
      planLineDisplay.value = steps.map((s, i) => planLineText(s, i))
      planTargetStrings.value = planLineDisplay.value.slice()
      return
    }
    if (rafPlan != null) {
      cancelAnimationFrame(rafPlan)
      rafPlan = null
    }
    if (!steps?.length) {
      planLineDisplay.value = []
      planTargetStrings.value = []
      return
    }
    const prevTargets = planTargetStrings.value || []
    const newTargets = steps.map((s, i) => planLineText(s, i))
    planTargetStrings.value = newTargets
    const cur = planLineDisplay.value.slice()
    while (cur.length < newTargets.length) cur.push('')
    if (cur.length > newTargets.length) cur.length = newTargets.length
    for (let i = 0; i < newTargets.length; i++) {
      const prev = prevTargets[i]
      const next = newTargets[i]
      if (prev !== next) {
        if (prev && next && next.startsWith(prev) && (cur[i] || '').length <= next.length) {
          // 同一行标题随 partial 变长：保留已打出的字
        } else {
          cur[i] = ''
        }
      }
    }
    planLineDisplay.value = cur
    runPlanTypewriter()
  },
  { deep: true }
)

/** detailLog / progressLog 合并为「执行过程」目标正文 */
const execStreamTarget = (s) => {
  if (s.detailLog && s.detailLog.length) {
    return s.detailLog.join('\n')
  }
  if (s.progressLog && s.progressLog.length) {
    return s.progressLog.join('\n')
  }
  return ''
}
const streamText = execStreamTarget

/** 思考推理 / 执行过程 / 入参说明：逐字 rAF（instantPlan 时直接全文）；观察结论走 llmConclusionViews 全文解析，不再打字机 */
const execTargets = ref([])
const reasoningTargets = ref([])
const paramsTargets = ref([])
const execStreamVisible = ref([])
const reasoningVisible = ref([])
const paramsStreamVisible = ref([])
let rafStream = null

const execStreamShown = (s, i) => {
  if (props.instantPlan) return execStreamTarget(s)
  return execStreamVisible.value[i] ?? ''
}
const paramsSummaryShown = (s, i) => {
  if (props.instantPlan) return String(s.paramsSummaryDraft || '')
  return paramsStreamVisible.value[i] ?? ''
}

const hasLlmDraft = (s) => !!(s.llmDraft && String(s.llmDraft).trim())
const hasParamsSummary = (s) => !!(s.paramsSummaryDraft && String(s.paramsSummaryDraft).trim())

/** 工具侧已有可观察产出（结果/定位/日志），再进入「决策与观察」；避免与「— 开始 —」同时出现 Planning */
const execPhaseFinished = (s) => {
  if (!s) return false
  if (s.status === 'completed' || s.status === 'error' || s.status === 'skipped') return true
  if (s.resultSummary && String(s.resultSummary).trim()) return true
  if (s.grepNavigation?.items?.length) return true
  const tx = streamText(s) || ''
  if (/—\s*结果\s*—|定位\s*\d|已生成|修改预览|批量修改|条匹配|预览/.test(tx)) return true
  const logs = [...(s.detailLog || []), ...(s.progressLog || [])].join('\n')
  if (/—\s*结果\s*—|已生成|修改预览|批量|完成|成功|预览/.test(logs)) return true
  return false
}

/** 执行已结束、正在等待观察流（仅副标题 Planning next moves） */
const showObserveWaiting = (s) => {
  if (s.status !== 'running') return false
  if (hasParamsSummary(s) || hasLlmDraft(s)) return false
  return execPhaseFinished(s)
}

/** 决策与观察：须等工具执行阶段有产出后再展示（含提前到达的入参/观察流） */
const showDecisionBlock = (s) => {
  if (hasParamsSummary(s) || hasLlmDraft(s)) {
    return execPhaseFinished(s) || s.status !== 'running'
  }
  return showObserveWaiting(s)
}

/** 执行区：工具过程 + 一行结果摘要 */
const showExecBlock = (s) => !!(streamText(s) || (s.resultSummary && String(s.resultSummary).trim()))

const runStreamTypewriters = () => {
  if (props.instantPlan) return
  const tick = () => {
    rafStream = null
    const n = props.steps?.length || 0
    if (!n) return
    let needMore = false
    const advance = (visibleRef, targetsRef) => {
      let cur = [...visibleRef.value]
      while (cur.length < n) cur.push('')
      if (cur.length > n) cur.length = n
      const tg = targetsRef.value
      for (let i = 0; i < n; i++) {
        const target = tg[i] || ''
        const shown = cur[i] || ''
        if (shown.length < target.length) {
          const backlog = target.length - shown.length
          const add = Math.min(backlog, Math.max(1, Math.ceil(backlog / 8)))
          cur[i] = target.slice(0, shown.length + add)
          needMore = true
        }
      }
      visibleRef.value = cur
    }
    advance(execStreamVisible, execTargets)
    advance(reasoningVisible, reasoningTargets)
    advance(paramsStreamVisible, paramsTargets)
    if (needMore) {
      rafStream = requestAnimationFrame(tick)
    }
  }
  if (rafStream != null) return
  rafStream = requestAnimationFrame(tick)
}

watch(
  () => props.steps,
  (steps) => {
    if (rafStream != null) {
      cancelAnimationFrame(rafStream)
      rafStream = null
    }
    if (!steps?.length) {
      execStreamVisible.value = []
      reasoningVisible.value = []
      paramsStreamVisible.value = []
      execTargets.value = []
      reasoningTargets.value = []
      paramsTargets.value = []
      thoughtPanelOpen.value = {}
      return
    }
    const n = steps.length
    const prevE = execTargets.value
    const prevR = reasoningTargets.value
    const prevP = paramsTargets.value

    const newE = steps.map((s) => execStreamTarget(s))
    const newR = steps.map((s) => {
      if ((s.agentThoughtDraft || '').trim()) return String(s.agentThoughtDraft || '')
      if ((s.thoughtReasoningDraft || '').trim() || (s.thoughtContentDraft || '').trim()) return ''
      return String(s.reasoningStepDraft || '')
    })
    const newP = steps.map((s) => String(s.paramsSummaryDraft || ''))

    execTargets.value = newE
    reasoningTargets.value = newR
    paramsTargets.value = newP

    if (props.instantPlan) {
      execStreamVisible.value = newE.slice()
      reasoningVisible.value = newR.slice()
      paramsStreamVisible.value = newP.slice()
      return
    }

    let exec = execStreamVisible.value.slice()
    let reas = reasoningVisible.value.slice()
    let par = paramsStreamVisible.value.slice()
    while (exec.length < n) exec.push('')
    while (reas.length < n) reas.push('')
    while (par.length < n) par.push('')
    exec.length = n
    reas.length = n
    par.length = n

    for (let i = 0; i < n; i++) {
      if (prevE[i] !== newE[i]) {
        if (
          !(
            prevE[i] &&
            newE[i] &&
            newE[i].startsWith(prevE[i]) &&
            (exec[i] || '').length <= newE[i].length
          )
        ) {
          exec[i] = ''
        }
      }
      if (prevR[i] !== newR[i]) {
        if (
          !(
            prevR[i] &&
            newR[i] &&
            newR[i].startsWith(prevR[i]) &&
            (reas[i] || '').length <= newR[i].length
          )
        ) {
          reas[i] = ''
        }
      }
      if (prevP[i] !== newP[i]) {
        if (
          !(
            prevP[i] &&
            newP[i] &&
            newP[i].startsWith(prevP[i]) &&
            (par[i] || '').length <= newP[i].length
          )
        ) {
          par[i] = ''
        }
      }
    }
    execStreamVisible.value = exec
    reasoningVisible.value = reas
    paramsStreamVisible.value = par
    runStreamTypewriters()
  },
  { deep: true }
)

onUnmounted(() => {
  if (rafPlan != null) cancelAnimationFrame(rafPlan)
  if (rafStream != null) cancelAnimationFrame(rafStream)
  if (thoughtTimer) {
    clearInterval(thoughtTimer)
    thoughtTimer = null
  }
})

const showLogBlock = (s) => {
  return (
    s.status === 'running' ||
    s.status === 'completed' ||
    s.status === 'error' ||
    (s.phaseWait && s.phaseWait.active) ||
    (s.detailLog && s.detailLog.length) ||
    (s.progressLog && s.progressLog.length) ||
    (s.llmDraft && String(s.llmDraft).trim()) ||
    (s.paramsSummaryDraft && String(s.paramsSummaryDraft).trim()) ||
    s.resultSummary ||
    (s.agentThoughtDraft && String(s.agentThoughtDraft).trim()) ||
    (s.reasoningStepDraft && String(s.reasoningStepDraft).trim()) ||
    (s.reasoningDecideDraft && String(s.reasoningDecideDraft).trim()) ||
    (s.thoughtReasoningDraft && String(s.thoughtReasoningDraft).trim()) ||
    (s.thoughtContentDraft && String(s.thoughtContentDraft).trim()) ||
    s.thoughtTiming ||
    (s.toolCall && s.toolCall.output && s.toolCall.output !== '执行中...') ||
    (s.grepNavigation && s.grepNavigation.items?.length)
  )
}

</script>

<style scoped>
/* 外层不框住「前置思考」，与首轮深度思考同级；步骤正文收在 agent-step-card 内 */
.agent-task-run {
  margin: 10px 0 14px;
  border: none;
  border-radius: 0;
  overflow: visible;
  background: transparent;
}

/* ReAct Thought：深度思考 reasoning（浅）/ content（亮） */
.agent-thought-deep-reason {
  color: #94a3b8 !important;
  background: rgba(30, 41, 59, 0.35);
  border-radius: 6px;
  padding: 6px 8px !important;
  margin-bottom: 8px !important;
  border: 1px solid rgba(148, 163, 184, 0.15);
}
.agent-thought-deep-content {
  color: #e2e8f0 !important;
  background: rgba(15, 23, 42, 0.55);
  border-radius: 6px;
  padding: 6px 8px !important;
  border: 1px solid rgba(148, 163, 184, 0.22);
}

.agent-thought-rich {
  white-space: normal;
}
.agent-thought-md {
  line-height: 1.55;
}
.agent-thought-md :deep(p) {
  margin: 0.35em 0;
}
.agent-thought-md :deep(p:first-child) {
  margin-top: 0;
}
.agent-thought-md :deep(p:last-child) {
  margin-bottom: 0;
}
.agent-thought-md :deep(ul),
.agent-thought-md :deep(ol) {
  margin: 0.35em 0;
  padding-left: 1.35em;
}
.agent-thought-md :deep(code) {
  background: rgba(30, 41, 59, 0.65);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 0.88em;
}
.agent-thought-md :deep(pre) {
  background: rgba(15, 23, 42, 0.65);
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.4em 0;
  font-size: 0.85em;
}
.agent-thought-findings {
  margin-top: 8px;
}
.agent-thought-findings-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88em;
}
.agent-thought-findings-table td {
  border: 1px solid rgba(148, 163, 184, 0.28);
  padding: 6px 8px;
  vertical-align: top;
}
.agent-thought-finding-type {
  width: 5.2rem;
  white-space: nowrap;
  font-weight: 600;
  font-size: 0.82em;
  text-transform: lowercase;
  color: #cbd5e1;
}
.agent-thought-finding-type[data-finding-type='success'] {
  color: #4ade80;
}
.agent-thought-finding-type[data-finding-type='info'] {
  color: #93c5fd;
}
.agent-thought-finding-type[data-finding-type='warning'] {
  color: #fbbf24;
}
.agent-thought-finding-type[data-finding-type='error'] {
  color: #f87171;
}
.agent-thought-finding-text {
  color: #e2e8f0;
  word-break: break-word;
}
.agent-thought-xml-tail {
  margin-top: 8px;
  margin-bottom: 0 !important;
  max-height: 140px;
  overflow: auto;
  font-size: 0.8em;
  opacity: 0.88;
  color: #cbd5e1 !important;
}

.agent-phase-wait {
  display: flex;
  align-items: center;
  min-height: 28px;
  margin-bottom: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.12);
  border: 1px solid rgba(59, 130, 246, 0.28);
}

.agent-phase-wait-dots {
  display: inline-flex;
  gap: 4px;
}

.agent-phase-wait-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #94a3b8;
  animation: agentPhaseWaitDot 1.4s infinite ease-in-out both;
}

.agent-phase-wait-dot:nth-child(1) {
  animation-delay: -0.32s;
}
.agent-phase-wait-dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes agentPhaseWaitDot {
  0%,
  80%,
  100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

.agent-plan {
  padding: 0;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 10px;
  background: rgba(15, 23, 42, 0.35);
}

.agent-plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  cursor: pointer;
  user-select: none;
  gap: 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.agent-plan-header:hover {
  background: rgba(59, 130, 246, 0.06);
}

.agent-plan-header:focus {
  outline: 1px solid rgba(59, 130, 246, 0.45);
  outline-offset: -1px;
}

.agent-plan-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.agent-plan-list-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.9;
}

.agent-plan-chevron {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.85;
}

.agent-plan-rows {
  padding: 0 12px 8px;
}

.agent-plan-title {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  letter-spacing: 0.02em;
}

.agent-plan-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  line-height: 1.45;
  color: #cbd5e1;
}

.agent-plan-row.is-running {
  color: #f1f5f9;
  background: rgba(59, 130, 246, 0.08);
  margin: 0 -8px;
  padding-left: 8px;
  padding-right: 8px;
  border-radius: 6px;
}

.agent-plan-row.is-done .agent-plan-text {
  opacity: 0.85;
}

.agent-plan-icon {
  flex-shrink: 0;
  width: 1.1em;
  text-align: center;
  font-size: 11px;
  margin-top: 1px;
}

.agent-plan-num {
  flex-shrink: 0;
  color: #94a3b8;
  min-width: 1.25em;
}

.agent-plan-text {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

.agent-plan-badge {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.2);
  color: #93c5fd;
}

.agent-logs {
  padding: 0 12px 8px;
}

.agent-step-outer {
  margin: 0;
}

.agent-step-divider--between {
  margin: 0 0 12px;
}

.agent-step-divider {
  height: 1px;
  background: rgba(148, 163, 184, 0.15);
  margin: 12px 0 14px;
}

/* 与 SimpleChatPanel 首轮 cursor-reasoning 对齐：前置思考独立块 */
.agent-preface-thought {
  margin: 6px 0 0;
  max-width: 100%;
}

.agent-preface-thought-inner {
  border: none;
  border-radius: 0;
  background: transparent;
  overflow: visible;
}

.agent-preface-thought-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 4px 0 8px;
  margin: 0;
  border: none;
  background: transparent;
  color: #858585;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  font-weight: 400;
}

.agent-preface-thought-summary:hover {
  color: #9d9d9d;
}

.agent-preface-thought-pill {
  color: #6b9bd1;
  font-weight: 500;
  letter-spacing: 0.01em;
}

.agent-preface-thought-meta {
  color: #858585;
  font-size: 11px;
  font-weight: 400;
}

.agent-preface-thought-chevron {
  margin-left: auto;
  opacity: 0.55;
  font-size: 10px;
  color: #858585;
}

.agent-preface-thought-feed {
  overflow: visible;
  max-height: none;
  padding: 0 0 8px;
  border: none;
  background: transparent;
}

.agent-preface-thought-plain {
  margin: 0;
  padding: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  font-size: 13px;
  line-height: 1.62;
  letter-spacing: 0.01em;
  color: #9d9d9d;
  white-space: pre-wrap;
  word-break: break-word;
}

.agent-preface-fallback {
  font-style: italic;
  opacity: 0.92;
}

.agent-preface-pre {
  max-height: 220px;
  overflow: auto;
  margin: 0;
  padding: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  font-size: 13px;
  line-height: 1.62;
  color: #9d9d9d;
  white-space: pre-wrap;
  word-break: break-word;
  background: transparent;
  border: none;
}

.agent-step-card {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  padding: 10px 12px 12px;
  background: rgba(15, 23, 42, 0.35);
}

/* 工具执行卡片：按工具区分左边线与底色（每种工具一种） */
.agent-tool-exec-card {
  border-left-width: 3px;
  border-left-style: solid;
}
.agent-tool-exec-card--grep {
  border-left-color: #3b82f6;
  background: rgba(30, 58, 95, 0.28);
}
.agent-tool-exec-card--modify {
  border-left-color: #f59e0b;
  background: rgba(120, 53, 15, 0.2);
}
.agent-tool-exec-card--create {
  border-left-color: #22c55e;
  background: rgba(20, 83, 45, 0.18);
}
.agent-tool-exec-card--search {
  border-left-color: #a855f7;
  background: rgba(88, 28, 135, 0.2);
}
.agent-tool-exec-card--database {
  border-left-color: #22d3ee;
  background: rgba(15, 118, 110, 0.18);
}
.agent-tool-exec-card--other {
  border-left-color: #94a3b8;
  background: rgba(15, 23, 42, 0.35);
}

.agent-tool-exec-body {
  margin-bottom: 0;
}

.agent-tool-exec-titlebar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px 2px;
}
.agent-tool-exec-icon {
  font-size: 14px;
  opacity: 0.9;
  line-height: 1;
}
.agent-tool-exec-name {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.02em;
  font-family: ui-monospace, 'Cascadia Code', Consolas, Menlo, monospace;
  color: #e2e8f0;
}

.agent-step-card--after-thought {
  margin-top: 4px;
}

/* 与「执行」卡片并列：观察/决策不包在 modify 执行块内 */
.agent-decision-panel {
  margin-top: 10px;
  padding: 10px 12px 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.28);
}

.agent-decide-eyebrow {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
  margin-bottom: 6px;
}

.agent-step-planning-inline {
  font-size: 11px;
  font-weight: 400;
  letter-spacing: 0.02em;
  text-transform: none;
  color: #64748b;
}

.agent-step-log-title {
  font-size: 12px;
  color: #e2e8f0;
  margin-bottom: 8px;
}

/* 分步日志：Thought → 执行卡片 → 决策与观察面板 */
.agent-step-phase {
  margin-bottom: 10px;
}

.agent-step-phase-eyebrow {
  font-size: 10px;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin: 0 0 4px 2px;
}

.agent-step-phase-eyebrow--inline {
  margin: 0;
  display: inline-block;
}

.agent-step-sublabel {
  font-size: 10px;
  color: #64748b;
  margin-bottom: 4px;
  font-weight: 500;
}

.agent-step-section--nest {
  margin-bottom: 8px;
}

.agent-step-pre--decide {
  color: #cbd5e1;
}

.agent-decision-observe-rich {
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(15, 23, 42, 0.55);
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
}

.agent-step-pre--exec {
  color: #f1f5f9;
  background: rgba(15, 23, 42, 0.72);
  border-color: rgba(148, 163, 184, 0.28);
}
.agent-step-pre--tool-grep {
  border-color: rgba(59, 130, 246, 0.35);
}
.agent-step-pre--tool-modify {
  border-color: rgba(245, 158, 11, 0.35);
}
.agent-step-pre--tool-create {
  border-color: rgba(34, 197, 94, 0.35);
}
.agent-step-pre--tool-search {
  border-color: rgba(168, 85, 247, 0.35);
}
.agent-step-pre--tool-database {
  border-color: rgba(34, 211, 238, 0.35);
}
.agent-step-pre--tool-other {
  border-color: rgba(148, 163, 184, 0.28);
}

.agent-step-exec-result {
  font-size: 12px;
  line-height: 1.55;
  color: #e2e8f0;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid rgba(34, 197, 94, 0.28);
  background: rgba(22, 101, 52, 0.14);
  margin-top: 4px;
  word-break: break-word;
}

.agent-step-section {
  margin-bottom: 10px;
}

.agent-step-label {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.agent-step-pre {
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.agent-step-pre--params {
  background: rgba(30, 41, 59, 0.65);
  color: #a5b4fc;
}

.agent-step-pre--stream {
  background: rgba(15, 23, 42, 0.55);
  color: #e2e8f0;
  max-height: 320px;
  overflow: auto;
}

.agent-step-result-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-step-result-value {
  font-size: 12px;
  color: #86efac;
  line-height: 1.5;
  word-break: break-word;
}

.agent-step-dur {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 4px;
}

.agent-step-dur strong {
  color: #cbd5e1;
  font-weight: 600;
}

.agent-step-grep-nav {
  margin-top: 4px;
}

.agent-grep-nav-details {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.35);
  overflow: hidden;
}

.agent-grep-nav-summary {
  list-style: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  user-select: none;
}

.agent-grep-nav-summary::-webkit-details-marker {
  display: none;
}

.agent-grep-nav-title::before {
  content: '🐛 ';
}

.agent-grep-nav-count {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.15);
  color: #93c5fd;
}

.agent-grep-nav-list {
  padding: 4px 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-grep-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: rgba(30, 41, 59, 0.45);
  color: #e2e8f0;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.agent-grep-nav-item:hover {
  background: rgba(51, 65, 85, 0.65);
}

.agent-grep-nav-icon {
  flex-shrink: 0;
  opacity: 0.85;
}

.agent-grep-nav-item-title {
  flex: 1;
  min-width: 0;
  word-break: break-word;
}

.agent-grep-nav-plan {
  flex-shrink: 0;
  font-size: 10px;
  color: #94a3b8;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(148, 163, 184, 0.12);
}
</style>
