<template>
  <div class="agent-task-run" v-if="steps && steps.length">
    <!-- 1) 顶部：紧凑计划（可折叠，与 TodoTimeline 同款图标/箭头） -->
    <div class="agent-plan">
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
          <span class="agent-plan-title">待执行步骤</span>
          <span v-if="statusText" class="agent-plan-status">{{ statusText }}</span>
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

    <!-- 2) 执行日志：每步一块，流式内容等宽 -->
    <div class="agent-logs">
      <div
        v-for="(s, i) in steps"
        :key="'l-' + i"
        v-show="showLogBlock(s)"
        class="agent-step-log-block"
      >
        <div v-if="i > 0" class="agent-step-divider" />
        <div class="agent-step-log-title">
          步骤 {{ i + 1 }}：<strong>{{ stepHeading(s) }}</strong>
        </div>
        <div v-if="stepThoughtLabel(s)" class="agent-step-thought-line">{{ stepThoughtLabel(s) }}</div>

        <div v-if="formatInputParams(s)" class="agent-step-section">
          <div class="agent-step-label">输入参数</div>
          <pre class="agent-step-pre agent-step-pre--params">{{ formatInputParams(s) }}</pre>
        </div>

        <div v-if="s.reasoningStepDraft && String(s.reasoningStepDraft).trim()" class="agent-step-section">
          <div class="agent-step-label">思考（本步）</div>
          <pre class="agent-step-pre agent-step-pre--stream agent-step-pre--reason">{{ reasoningShown(s, i) }}</pre>
        </div>

        <div v-if="hasLlmDraft(s)" class="agent-step-section">
          <div class="agent-step-label">决策 / 观察</div>
          <pre class="agent-step-pre agent-step-pre--stream">{{ llmStreamShown(s, i) }}</pre>
        </div>

        <div v-if="streamText(s)" class="agent-step-section">
          <div class="agent-step-label">执行过程</div>
          <pre class="agent-step-pre agent-step-pre--stream">{{ execStreamShown(s, i) }}</pre>
        </div>

        <div v-if="s.resultSummary" class="agent-step-section agent-step-result-row">
          <span class="agent-step-label">执行结果</span>
          <span class="agent-step-result-value">{{ s.resultSummary }}</span>
        </div>

        <div v-if="s.stepDurationMs != null && s.stepDurationMs >= 0" class="agent-step-dur">
          耗时 <strong>{{ (s.stepDurationMs / 1000).toFixed(2) }}s</strong>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'
import todoListIcon from '../assets/todo-list-icon.svg'
import chevronRightIcon from '../assets/chevron-right-qoder.png'
import chevronDownIcon from '../assets/chevron-down-qoder.png'

const props = defineProps({
  steps: { type: Array, default: () => [] },
  /** 顶部右侧状态文案，如「正在执行 1 个步骤…」 */
  statusText: { type: String, default: '' },
  /** 历史会话等：计划行不要逐字动画，直接显示全文 */
  instantPlan: { type: Boolean, default: false }
})

const planExpanded = ref(true)

const togglePlan = () => {
  planExpanded.value = !planExpanded.value
}

const planIcon = (s) => {
  if (s.status === 'completed') return '✅'
  if (s.status === 'running') return '▢'
  if (s.status === 'skipped') return '⏭'
  if (s.status === 'error') return '⚠'
  return '▢'
}

/** Cursor 式：本步 decide/observe 的 Thought briefly / for X.Xs */
const stepThoughtLabel = (s) => {
  const t = s.thoughtTiming
  if (!t || t.durationMs == null) return ''
  const thr = t.briefThresholdMs ?? 800
  if (t.kind === 'brief' || t.durationMs < thr) return 'Thought briefly'
  return `Thought for ${(t.durationMs / 1000).toFixed(1)}s`
}

const stepHeading = (s) => {
  const t = s.title || '工具'
  if (t === 'grep') return '使用 grep 工具'
  if (t === 'modify') return '使用 modify 工具'
  if (t === 'create') return '使用 create 工具'
  if (t === 'search') return '使用 search 工具'
  return `使用 ${t} 工具`
}

const planLineText = (s, i) => {
  const raw = (s.originalTodo || s.title || `步骤 ${i + 1}`).trim()
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

/** 执行过程 / 思考 / llmDraft：逐字 rAF（instantPlan 时直接全文） */
const execTargets = ref([])
const reasoningTargets = ref([])
const llmTargets = ref([])
const execStreamVisible = ref([])
const reasoningVisible = ref([])
const llmStreamVisible = ref([])
let rafStream = null

const execStreamShown = (s, i) => {
  if (props.instantPlan) return execStreamTarget(s)
  return execStreamVisible.value[i] ?? ''
}
const reasoningShown = (s, i) => {
  if (props.instantPlan) return String(s.reasoningStepDraft || '')
  return reasoningVisible.value[i] ?? ''
}
const llmStreamShown = (s, i) => {
  if (props.instantPlan) return String(s.llmDraft || '')
  return llmStreamVisible.value[i] ?? ''
}

const hasLlmDraft = (s) => !!(s.llmDraft && String(s.llmDraft).trim())

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
    advance(llmStreamVisible, llmTargets)
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
      llmStreamVisible.value = []
      execTargets.value = []
      reasoningTargets.value = []
      llmTargets.value = []
      return
    }
    const n = steps.length
    const prevE = execTargets.value
    const prevR = reasoningTargets.value
    const prevL = llmTargets.value

    const newE = steps.map((s) => execStreamTarget(s))
    const newR = steps.map((s) => String(s.reasoningStepDraft || ''))
    const newL = steps.map((s) => String(s.llmDraft || ''))

    execTargets.value = newE
    reasoningTargets.value = newR
    llmTargets.value = newL

    if (props.instantPlan) {
      execStreamVisible.value = newE.slice()
      reasoningVisible.value = newR.slice()
      llmStreamVisible.value = newL.slice()
      return
    }

    let exec = execStreamVisible.value.slice()
    let reas = reasoningVisible.value.slice()
    let llm = llmStreamVisible.value.slice()
    while (exec.length < n) exec.push('')
    while (reas.length < n) reas.push('')
    while (llm.length < n) llm.push('')
    exec.length = n
    reas.length = n
    llm.length = n

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
      if (prevL[i] !== newL[i]) {
        if (
          !(
            prevL[i] &&
            newL[i] &&
            newL[i].startsWith(prevL[i]) &&
            (llm[i] || '').length <= newL[i].length
          )
        ) {
          llm[i] = ''
        }
      }
    }
    execStreamVisible.value = exec
    reasoningVisible.value = reas
    llmStreamVisible.value = llm
    runStreamTypewriters()
  },
  { deep: true }
)

onUnmounted(() => {
  if (rafPlan != null) cancelAnimationFrame(rafPlan)
  if (rafStream != null) cancelAnimationFrame(rafStream)
})

const showLogBlock = (s) => {
  return (
    s.status === 'running' ||
    s.status === 'completed' ||
    s.status === 'error' ||
    (s.detailLog && s.detailLog.length) ||
    (s.progressLog && s.progressLog.length) ||
    (s.llmDraft && String(s.llmDraft).trim()) ||
    s.resultSummary ||
    (s.reasoningStepDraft && String(s.reasoningStepDraft).trim()) ||
    s.thoughtTiming ||
    (s.toolCall && s.toolCall.output && s.toolCall.output !== '执行中...')
  )
}

const formatInputParams = (s) => {
  if (s.inputParams && typeof s.inputParams === 'object' && Object.keys(s.inputParams).length) {
    try {
      return JSON.stringify(s.inputParams, null, 2)
    } catch {
      return String(s.inputParams)
    }
  }
  return ''
}

</script>

<style scoped>
.agent-task-run {
  margin: 10px 0 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.35);
}

.agent-plan {
  padding: 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.25);
}

.agent-plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  cursor: pointer;
  user-select: none;
  gap: 10px;
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

.agent-plan-status {
  font-size: 11px;
  color: #93c5fd;
  margin-left: 6px;
  flex-shrink: 0;
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
  padding: 10px 12px 12px;
}

.agent-step-divider {
  height: 1px;
  background: rgba(148, 163, 184, 0.15);
  margin: 12px 0 14px;
}

.agent-step-log-title {
  font-size: 12px;
  color: #e2e8f0;
  margin-bottom: 8px;
}

.agent-step-thought-line {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.95);
  margin: -4px 0 10px;
  padding-left: 2px;
}

.agent-step-pre--reason {
  max-height: 160px;
  color: #cbd5e1;
  background: rgba(30, 41, 59, 0.4);
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
</style>
