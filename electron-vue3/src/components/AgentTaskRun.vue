<template>
  <div class="agent-task-run" v-if="steps && steps.length">
    <!-- Thought → 规划备忘 → 执行 → 决策与观察（推断与分支叙述只在「思考」折叠正文内展示，眉标与步骤序号对齐） -->
    <div class="agent-logs">
      <div
        v-for="(s, i) in steps"
        :key="'l-' + i"
        class="agent-step-wrap"
      >
        <div v-if="showPreparingNextCue(i)" class="agent-between-steps-cue" role="status">
          {{ preparingNextCueText(i) }}
        </div>
        <div v-show="showLogBlock(s, i)" class="agent-step-outer">
        <div v-if="i > 0" class="agent-step-divider agent-step-divider--between" />
        <!-- 第 0 行：THINK 与首条待办同捆一步；眉标已隐藏，不显示步骤序号 -->
        <!-- <div class="agent-step-eyebrow" role="presentation">
          <span class="agent-step-eyebrow-bar" aria-hidden="true" />
          <span class="agent-step-eyebrow-text">{{ stepEyebrowLabel(i) }}</span>
        </div> -->

        <!-- Thought：标题字本身渐变（执行中）；无左侧竖条；完成后右侧耗时；结束后默认折叠 -->
        <div
          v-if="hasStepThought(s) && thoughtUiDotsOnly(s) && !(i === 0 && hidePrefacePlaceholder)"
          class="agent-preface-thought agent-preface-thought--dots-only"
        >
          <button
            type="button"
            class="agent-step-fold-head agent-step-fold-head--thought"
            :aria-expanded="true"
            disabled
          >
            <img
              class="agent-step-fold-thought-icon"
              :src="deepThinkingIcon"
              alt=""
              aria-hidden="true"
            />
            <span class="agent-step-fold-main">
              <span class="agent-step-fold-label agent-step-fold-label--thought-shimmer">{{ t('agentTask.thinking') }}</span>
            </span>
            <span class="agent-step-fold-chevron agent-step-fold-chevron--muted" aria-hidden="true">▾</span>
          </button>
          <div class="agent-phase-wait" role="status" :aria-label="t('agentTask.waitAria')">
            <span class="agent-phase-wait-dots" aria-hidden="true">
              <span class="agent-phase-wait-dot"></span>
              <span class="agent-phase-wait-dot"></span>
              <span class="agent-phase-wait-dot"></span>
            </span>
          </div>
        </div>
        <div
          v-else-if="hasStepThought(s) && !(i === 0 && hidePrefacePlaceholder)"
          class="agent-preface-thought"
        >
          <div class="agent-preface-thought-inner">
            <button
              type="button"
              class="agent-step-fold-head agent-step-fold-head--thought"
              :aria-expanded="thoughtOpen(i)"
              :title="thoughtOpen(i) ? t('agentTask.clickCollapse') : t('agentTask.clickExpand')"
              @click="toggleThought(i)"
            >
              <img
                class="agent-step-fold-thought-icon"
                :src="deepThinkingIcon"
                alt=""
                aria-hidden="true"
              />
              <span class="agent-step-fold-main">
                <span class="agent-step-fold-label-row">
                  <span
                    class="agent-step-fold-label"
                    :class="{ 'agent-step-fold-label--thought-shimmer': thoughtHeaderShimmer(s) }"
                  >{{ thoughtFoldLeftLabel(s) }}</span>
                  <span
                    v-if="thoughtFoldShowSpinner(s)"
                    class="agent-step-fold-spinner"
                    aria-hidden="true"
                  />
                  <span
                    v-else-if="thoughtFoldDurationRight(s)"
                    class="agent-step-fold-duration"
                  >{{ thoughtFoldDurationRight(s) }}</span>
                </span>
                <span
                  v-if="thoughtSummaryVisible(s)"
                  class="agent-step-think-summary"
                >{{ thoughtSummaryText(s) }}</span>
              </span>
              <span class="agent-step-fold-chevron" aria-hidden="true">{{ thoughtOpen(i) ? '▾' : '▸' }}</span>
            </button>
            <div
              v-show="
                thoughtOpen(i) &&
                (thoughtBodySubstantive(s) ||
                  (s.phaseWait && s.phaseWait.active) ||
                  hasReasoningBody(s))
              "
              class="agent-preface-thought-feed"
            >
              <!-- ReAct Thought：自然语言 Markdown；后端已分轨不推送原始 XML -->
              <div
                v-if="s.phaseWait?.active && !thoughtBodySubstantive(s)"
                class="agent-phase-wait"
                role="status"
                :aria-label="t('agentTask.waitAria')"
              >
                <span class="agent-phase-wait-dots" aria-hidden="true">
                  <span class="agent-phase-wait-dot"></span>
                  <span class="agent-phase-wait-dot"></span>
                  <span class="agent-phase-wait-dot"></span>
                </span>
              </div>
              <!-- 流式中勿对全文 marked.parse：会主线程 O(n²) 阻塞 paint，表现为收完才一次性出现；结束后仍用 Markdown -->
              <pre
                v-if="showThoughtReasoningBlock(s) && thoughtReasoningUsePlainStream(s)"
                class="agent-thought-deep-reason agent-thought-rich agent-thought-stream-plain"
              >{{ collapseThoughtDisplayNewlines(thoughtReasoningShown(s, i)) }}</pre>
              <div
                v-else-if="showThoughtReasoningBlock(s)"
                class="agent-thought-deep-reason agent-thought-rich reasoning-markdown agent-thought-md"
                v-html="formatThoughtMarkdown(thoughtReasoningShown(s, i))"
              />
              <pre
                v-if="showThoughtContentBlock(s) && thoughtContentUsePlainStream(s)"
                class="agent-thought-deep-content agent-thought-rich agent-thought-stream-plain"
              >{{ collapseThoughtDisplayNewlines(thoughtContentRaw(s)) }}</pre>
              <div
                v-else-if="showThoughtContentBlock(s)"
                class="agent-thought-deep-content agent-thought-rich reasoning-markdown agent-thought-md"
                v-html="formatThoughtMarkdown(thoughtContentRaw(s))"
              />
              <!-- 正文已出、正在收 <decision>/todo_list 等隐藏 XML：眉标墙钟已冻结，此处用三点表示仍在解析 -->
              <div
                v-if="s.phaseWait?.active && thoughtBodySubstantive(s)"
                class="agent-phase-wait agent-phase-wait--after-thought"
                role="status"
                :aria-label="t('agentTask.waitAria')"
              >
                <span class="agent-phase-wait-dots" aria-hidden="true">
                  <span class="agent-phase-wait-dot"></span>
                  <span class="agent-phase-wait-dot"></span>
                  <span class="agent-phase-wait-dot"></span>
                </span>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="isPreparingNextStepWait(s) && !showPreparingNextCue(i)"
          class="agent-between-steps-cue agent-between-steps-cue--inline"
          role="status"
        >
          {{ preparingNextCueText(i) }}
        </div>

        <!-- 规划备忘：仅展示后端下发的计划行（planMemoRows），与执行 steps 解耦 -->
        <div
          v-if="i === 0 && showPlanMemoBlock"
          class="agent-plan agent-plan--after-thought"
        >
          <div
            class="agent-plan-header"
            role="button"
            tabindex="0"
            :title="planExpanded ? t('agentTask.clickCollapse') : t('agentTask.clickExpand')"
            @click="togglePlan"
            @keydown.enter.prevent="togglePlan"
            @keydown.space.prevent="togglePlan"
          >
            <div class="agent-plan-header-left">
              <img class="agent-plan-list-icon" :src="todoListIcon" alt="" />
              <span class="agent-plan-title">{{ t('agentTask.planMemo') }}</span>
            </div>
            <img
              class="agent-plan-chevron"
              :src="planExpanded ? chevronDownIcon : chevronRightIcon"
              alt=""
              :title="planExpanded ? t('agentTask.clickCollapse') : t('agentTask.clickExpand')"
            />
          </div>
          <div v-show="planExpanded" class="agent-plan-rows">
            <div
              v-for="(ps, pi) in planMemoRowModels"
              :key="'p-' + pi"
              class="agent-plan-row"
              :class="{
                'is-running': ps.status === 'running',
                'is-done': ps.status === 'completed',
                'is-skip': ps.status === 'skipped',
                'is-err': ps.status === 'error' || ps.status === 'failed'
              }"
            >
              <span class="agent-plan-icon" aria-hidden="true">{{ planIcon(ps) }}</span>
              <span class="agent-plan-num">{{ pi + 1 }}.</span>
              <span class="agent-plan-text">{{ planRowShown(ps, pi) }}</span>
              <span v-if="ps.status === 'running'" class="agent-plan-badge">{{ t('agentTask.running') }}</span>
            </div>
          </div>
        </div>

        <!-- 工具执行：与思考同款折叠头；流式日志在下方；结束后默认收起 -->
        <div
          v-if="showToolExecCard(s)"
          class="agent-tool-exec-log-block"
          :class="{
            'agent-tool-exec-log-block--after-thought':
              hasStepThought(s) || (i === 0 && showPlanMemoBlock)
          }"
          :data-agent-step="i"
        >
          <button
            type="button"
            class="agent-step-fold-head agent-step-fold-head--tool"
            :aria-expanded="toolExecOpen(i)"
            :title="toolExecOpen(i) ? t('agentTask.clickCollapse') : t('agentTask.clickExpand')"
            @click="toggleToolExec(i)"
          >
            <span class="agent-step-fold-icon" aria-hidden="true">
              <span
                v-if="execToolKind(s) === 'delete'"
                class="agent-step-fold-icon-tint"
                :style="deleteToolIconMaskStyle"
              />
              <span
                v-else-if="execToolKind(s) === 'copy'"
                class="agent-step-fold-icon-tint"
                :style="copyToolIconMaskStyle"
              />
              <img
                v-else-if="execToolKind(s) === 'cdp'"
                class="agent-step-fold-icon-img"
                :src="cdpIcon"
                alt=""
                aria-hidden="true"
              />
              <template v-else>{{ toolFoldIcon(s) }}</template>
            </span>
            <span class="agent-step-fold-main">
              <span class="agent-step-fold-label-row">
                <span
                  class="agent-step-fold-label"
                  :class="{ 'agent-step-fold-label--thought-shimmer': toolExecRunning(s) }"
                >{{ toolFoldDisplayName(s) }}</span>
                <span
                  v-if="toolFoldShowSpinner(s)"
                  class="agent-step-fold-spinner"
                  aria-hidden="true"
                />
                <span
                  v-else-if="toolFoldDuration(s)"
                  class="agent-step-fold-duration"
                >{{ toolFoldDuration(s) }}</span>
              </span>
            </span>
            <span class="agent-step-fold-chevron" aria-hidden="true">{{ toolExecOpen(i) ? '▾' : '▸' }}</span>
          </button>
          <div
            v-show="toolExecOpen(i) && showExecBlock(s)"
            class="agent-tool-exec-log-body"
          >
            <pre
              v-if="String(execLogMergedText(s, i) || '').trim()"
              class="agent-tool-exec-log-pre"
            >{{ execLogMergedText(s, i) }}</pre>
          </div>

          <div
            v-if="s.grepNavigation && s.grepNavigation.type === 'multiple' && s.grepNavigation.items?.length"
            class="agent-step-section agent-step-grep-nav"
          >
            <div class="agent-step-label">{{ t('agentTask.locateResults') }}</div>
            <details class="agent-grep-nav-details" open>
              <summary class="agent-grep-nav-summary">
                <span class="agent-grep-nav-title">{{ grepNavSectionTitle(s.grepNavigation.items) }}</span>
                <span class="agent-grep-nav-count">{{ t('chat.navRecords', { n: s.grepNavigation.items.length }) }}</span>
              </summary>
              <div class="agent-grep-nav-list-wrap">
                <div
                  class="agent-grep-nav-list-shell"
                  :class="{ 'is-collapsed': grepNavStepListCollapsed(s, i) }"
                >
                  <div class="agent-grep-nav-list-inner">
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
                  <div
                    v-if="grepNavStepListCollapsed(s, i)"
                    class="agent-grep-nav-list-fade"
                    aria-hidden="true"
                  />
                </div>
                <button
                  v-if="grepNavNeedsCollapseForStep(s)"
                  type="button"
                  class="agent-grep-nav-expand"
                  @click.stop="toggleGrepNavStepExpand(i)"
                >
                  <span>{{
                    grepNavStepListExpanded(i) ? t('chat.navCollapseList') : t('chat.navExpandAll')
                  }}</span>
                  <span class="agent-grep-nav-expand-chevron" aria-hidden="true">{{
                    grepNavStepListExpanded(i) ? '▾' : '▸'
                  }}</span>
                </button>
              </div>
            </details>
          </div>
        </div>

        <!-- 决策观察内容：去标题、纯内容无缝衔接，视觉与对话面板统一 -->
        <div v-if="showDecisionBlock(s)" class="agent-decision-panel agent-decision-panel--plain">
          <div
            v-if="hasLlmDraft(s) && String(s.llmDraft || '').trim()"
            class="agent-decision-observe-rich agent-decision-observe-rich--plain agent-thought-rich agent-step-pre--decide reasoning-markdown agent-thought-md"
            v-html="formatThoughtMarkdown(String(s.llmDraft || ''))"
          />
          <pre
            v-else-if="hasParamsSummary(s)"
            class="agent-step-pre agent-step-pre--params agent-step-pre--stream agent-step-pre--decide agent-step-pre--plain"
          >{{ paramsSummaryShown(s, i) }}</pre>
          <div v-if="showObserveWaiting(s)" class="agent-step-planning-inline agent-step-planning-inline--plain">
            {{ t('agentTask.planningNextMoves') }}
          </div>
        </div>
        </div>
        <!-- modify 沙箱锚点：父组件用 Teleport 将沙箱内容挂入此槽位，紧跟最后一个 modify 工具步 -->
        <slot
          v-if="sandboxAfterModifyStepIndex >= 0 && sandboxAfterModifyStepIndex === i"
          name="modifySandbox"
        />
        <slot
          v-if="sandboxAfterDeleteStepIndex >= 0 && sandboxAfterDeleteStepIndex === i"
          name="deleteSandbox"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted, computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import todoListIcon from '../assets/todo-list-icon.svg'
import deepThinkingIcon from '../assets/deep-thinking-icon.svg'
import chevronRightIcon from '../assets/chevron-right-qoder.png'
import chevronDownIcon from '../assets/chevron-down-qoder.png'
import toolDeleteIcon from '../assets/tool-delete.png'
import toolCopyIcon from '../assets/tool-copy.png'
import cdpIcon from '../assets/cdp-icon.png'
import { mergedThoughtReasoningProseFromStep } from '../composables/thoughtSnapshot.js'
import { stripReasoningChannelArtifacts } from '../utils/stripReasoningChannelArtifacts.js'
import {
  isInternalMacroThoughtSummary,
  sanitizeThoughtSummaryForDisplay
} from '../utils/macroThoughtSummary.js'

/** 与 .agent-step-fold-head--tool 文案色一致（#7dd3fc），mask 上色使 PNG 与「思考」图标同色系 */
const deleteToolIconMaskStyle = {
  WebkitMaskImage: `url(${toolDeleteIcon})`,
  maskImage: `url(${toolDeleteIcon})`
}
const copyToolIconMaskStyle = {
  WebkitMaskImage: `url(${toolCopyIcon})`,
  maskImage: `url(${toolCopyIcon})`
}

const { t } = useI18n()

const props = defineProps({
  steps: { type: Array, default: () => [] },
  /** 后端下发的计划行（plan / todos）；无则 undefined，顶部「规划备忘」不渲染 */
  planMemoRows: { type: Array, default: undefined },
  /** 历史会话等：计划行不要逐字动画，直接显示全文 */
  instantPlan: { type: Boolean, default: false },
  /** 为 true 时思考/执行区目标正文一次性对齐（无二次 rAF 打字机）。默认 false：与 SimpleChatPanel 顶部一致，步骤内 Thought 逐字出字 */
  realtimeStream: { type: Boolean, default: false },
  /** 与 v1 plan.suppress_plan_ui 对齐：隐藏顶部「规划备忘」，仍保留下方步骤执行区 */
  suppressPlanOverview: { type: Boolean, default: false },
  /**
   * hello 占位 step 已挂起但 THINK 正文尚在消息层：在首段实质思考出现前隐藏本步 Thought 区，
   * 仅由 SimpleChatPanel 顶部一组「...」占位，避免与 AgentTaskRun 内第二、第三段「...」重复。
   */
  hidePrefacePlaceholder: { type: Boolean, default: false },
  /**
   * 与 SimpleChatPanel 沙箱「是否仍有待采纳」对齐。为 false 时，批量 modify 步骤里原先写死的「请在沙箱确认」摘要改为已闭环文案。
   */
  modifySandboxPending: { type: Boolean, default: true },
  /**
   * ≥0：在该步骤（最后一个 modify 工具步）之后渲染 modifySandbox 插槽，供父组件 Teleport 锚点。
   * -1：不内嵌（沙箱仍在时间线下方）。
   */
  sandboxAfterModifyStepIndex: { type: Number, default: -1 },
  /**
   * ≥0：在该步骤（最后一个 delete 工具步）之后渲染 deleteSandbox（删除预览卡片紧跟 delete 行）。
   * -1：不内嵌（由父组件在任务流下方整体渲染，兼容旧布局）。
   */
  sandboxAfterDeleteStepIndex: { type: Number, default: -1 }
})

const emit = defineEmits(['grep-bug-click'])

marked.setOptions({ gfm: true, breaks: true })

const formatThoughtMarkdown = (text) => {
  const t = stripReasoningChannelArtifacts(
    String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/[\u200B-\u200D\uFEFF\u2060]/g, '')
      .trim()
  )
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  if (!t) return ''
  try {
    return marked.parse(t, { gfm: true, breaks: true })
  } catch {
    return ''
  }
}

const collapseThoughtDisplayNewlines = (s) =>
  String(s || '')
    .replace(/\r\n/g, '\n')
    .replace(/[\u200B-\u200D\uFEFF\u2060]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

const planExpanded = ref(true)

const togglePlan = () => {
  planExpanded.value = !planExpanded.value
}

/** 与执行 steps 对齐下标时同步勾选状态（plan / todos 与步序一致时） */
const planMemoRowModels = computed(() => {
  const raw = props.planMemoRows
  if (!Array.isArray(raw) || raw.length === 0) return []
  const st = props.steps || []
  return raw.map((item, pi) => {
    const title =
      typeof item === 'string'
        ? item
        : String((item && (item.description || item.name || item.title || item.text)) || '').trim()
    const exec = st[pi]
    return {
      title,
      originalTodo: title,
      status: exec?.status || 'pending'
    }
  })
})

const showPlanMemoBlock = computed(
  () => planMemoRowModels.value.length > 0 && !props.suppressPlanOverview
)

const grepNavSectionTitle = (items) => {
  if (!items?.length) return t('chat.grepJumpList')
  const ts = [...new Set(items.map((i) => (i?.target || 'bug').toString().toLowerCase()))]
  const labelKey = {
    bug: 'chat.navLabelBug',
    badcase: 'chat.navLabelBadcase',
    testcase: 'chat.navLabelTestcase',
    card: 'chat.navLabelCard'
  }
  if (ts.length === 1) {
    const k = ts[0]
    return t('chat.grepJumpTo', { type: t(labelKey[k] || 'chat.navLabelBug') })
  }
  return t('chat.grepJumpList')
}

const grepNavItemTitle = (navItem) => (navItem && (navItem.title || navItem.bug_title)) || ''

/** 步骤内 grep 导航：条数多时默认收起 + 底部渐变，与 SimpleChatPanel 一致 */
const GREP_NAV_COLLAPSE_AFTER = 5
const grepNavStepExpandedMap = reactive({})
const grepNavNeedsCollapseForStep = (s) =>
  (s?.grepNavigation?.items?.length || 0) > GREP_NAV_COLLAPSE_AFTER
const grepNavStepListExpanded = (stepIdx) => !!grepNavStepExpandedMap[stepIdx]
const grepNavStepListCollapsed = (s, stepIdx) =>
  grepNavNeedsCollapseForStep(s) && !grepNavStepListExpanded(stepIdx)
const toggleGrepNavStepExpand = (stepIdx) => {
  grepNavStepExpandedMap[stepIdx] = !grepNavStepExpandedMap[stepIdx]
}

const planIcon = (s) => {
  if (s.status === 'completed') return '✅'
  if (s.status === 'running') return '▢'
  if (s.status === 'skipped') return '⏭'
  if (s.status === 'error' || s.status === 'failed') return '⚠'
  return '▢'
}

/** 本步思考 / 工具日志：用户手动展开覆盖默认（默认：思考与工具在结束后自动折叠） */
const thoughtPanelOpen = ref({})
const toolPanelOpen = ref({})

/** plan 替换后首轮可能仍为 pending 但已有思考草稿与 stepStartedAt：须 tick 才能眉标秒数跟 SSE 涨 */
const stepWantsThoughtWallClockTick = (s) => {
  if (!s || s.stepStartedAt == null || s.thoughtPhaseEndAtMs != null) return false
  const drafts = `${s.thoughtReasoningDraft || ''}${s.thoughtContentDraft || ''}${s.agentThoughtDraft || ''}`
  const vis = drafts.replace(/[\u200B-\u200D\uFEFF\u2060]/g, '').trim()
  if (vis.length < 2 || !/[\u4e00-\u9fa5A-Za-z0-9]/.test(vis)) return false
  return s.status === 'running' || s.status === 'pending'
}

/** 有步骤 running 时定时刷新，使「Thought for X.Xs」随本步耗时递增（对齐 Cursor，而非静态 Thinking…） */
const thoughtUiTick = ref(0)
let thoughtTimer = null
watch(
  () =>
    (props.steps || []).some((s) => s.status === 'running' || stepWantsThoughtWallClockTick(s)),
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
 * 合并 thoughtReasoningDraft + agentThought*，避免计划到达前后正文写在不同字段时被截断或隐藏。
 */
const thoughtReasoningRaw = (s) => {
  if (s.thoughtReasoningSnapshot) return String(s.thoughtReasoningSnapshot)
  return mergedThoughtReasoningProseFromStep(s)
}
/**
 * 深度思考 content 侧（一般为空：XML 不再注入此处）
 * 过滤掉XML标签内容，避免在思考区显示原始XML结构（如 <decision> 内容）
 * 这些内容应该在 phase_wait 加载效果期间隐藏
 */
const thoughtContentRaw = (s) => {
  if (s.thoughtContentSnapshot) return String(s.thoughtContentSnapshot)
  const raw = String(s.thoughtContentDraft || '')
  // 过滤掉包含XML标签的内容（如 <decision>, <execute>, <tool>, <params> 等）
  // 这些是结构化输出，不应显示在思考区
  if (/<decision|<execute|<tool\b|<params|<reason\b|<result\b/i.test(raw)) {
    return ''
  }
  return raw
}

const hasReasoningBody = (s) =>
  !!(String(thoughtReasoningRaw(s)).trim() || String(thoughtContentRaw(s)).trim())

/** 与 SimpleChatPanel 一致：流式首包常只有括号/标点，不单独占一块 Markdown */
const _thoughtStripVisible = (t) => String(t || '').replace(/\u200b/g, '').trim()
const _thoughtHasMeaningfulChar = (t) => /[\u4e00-\u9fa5A-Za-z0-9]/.test(_thoughtStripVisible(t))
const thoughtReasoningMarkdownVisible = (s) =>
  _thoughtStripVisible(thoughtReasoningRaw(s)).length >= 2 && _thoughtHasMeaningfulChar(thoughtReasoningRaw(s))
const thoughtContentMarkdownVisible = (s) =>
  _thoughtStripVisible(thoughtContentRaw(s)).length >= 2 && _thoughtHasMeaningfulChar(thoughtContentRaw(s))
/** running/pending 流式：≥1 个有效字符即算有正文（plain 预渲染，不跑 Markdown） */
const thoughtReasoningStreamChunkVisible = (s) => {
  const raw = thoughtReasoningRaw(s)
  return _thoughtStripVisible(raw).length >= 1 && _thoughtHasMeaningfulChar(raw)
}
const thoughtContentStreamChunkVisible = (s) => {
  const raw = thoughtContentRaw(s)
  return _thoughtStripVisible(raw).length >= 1 && _thoughtHasMeaningfulChar(raw)
}
const thoughtBodySubstantive = (s) =>
  thoughtReasoningMarkdownVisible(s) ||
  thoughtContentMarkdownVisible(s) ||
  thoughtReasoningStreamChunkVisible(s) ||
  thoughtContentStreamChunkVisible(s)

const thoughtReasoningUsePlainStream = (s) =>
  !!s && !s.thoughtReasoningSnapshot && (s.status === 'running' || s.status === 'pending')
const thoughtContentUsePlainStream = (s) =>
  !!s && !s.thoughtContentSnapshot && (s.status === 'running' || s.status === 'pending')

/** 流式 running：展示 reasoningVisible[i]，与 watch 内 reasoningTargets（合并正文）一致；勿直接绑 thoughtReasoningRaw 全文 */
const thoughtReasoningShown = (s, i) => {
  if (props.instantPlan || props.realtimeStream) return thoughtReasoningRaw(s)
  if (thoughtReasoningUsePlainStream(s)) {
    const idx = typeof i === 'number' ? i : 0
    return reasoningVisible.value[idx] ?? ''
  }
  return thoughtReasoningRaw(s)
}

/** 流式：≥1 有效字即展示 plain；终态：≥2 字才用 Markdown 块（避免碎标点） */
const showThoughtReasoningBlock = (s) => {
  const raw = thoughtReasoningRaw(s)
  if (!String(raw).trim()) return false
  if (s.thoughtReasoningSnapshot) return true
  if (s.status === 'completed' || s.status === 'error' || s.status === 'skipped') return true
  if (s.status === 'running' || s.status === 'pending') return thoughtReasoningStreamChunkVisible(s)
  return thoughtReasoningMarkdownVisible(s)
}
const showThoughtContentBlock = (s) => {
  const raw = thoughtContentRaw(s)
  if (!String(raw).trim()) return false
  if (s.thoughtContentSnapshot) return true
  if (s.status === 'completed' || s.status === 'error' || s.status === 'skipped') return true
  if (s.status === 'running' || s.status === 'pending') return thoughtContentStreamChunkVisible(s)
  return thoughtContentMarkdownVisible(s)
}

/**
 * 尚无≥2 字有意义正文时：不显示孤零零的「思考」标题（仅 pill、无下文），改与 phase_wait 一致只显示三点。
 * 覆盖：本步已 running 且已记 stepStartedAt，但 decide/Thought 流尚未到达的前置间隙（原会先闪一帧 agentTask.thought）。
 */
const isPreparingNextStepWait = (s) => {
  if (!s?.phaseWait?.active) return false
  const k = String(s.phaseWait.kind || '').toLowerCase()
  return k === 'preparing_next_step' || k === 'macro_params_llm'
}

const thoughtUiDotsOnly = (s) => {
  if (s?.macroExecOnly) return false
  if (isPreparingNextStepWait(s)) return false
  if (thoughtBodySubstantive(s)) return false
  if (s.phaseWait && s.phaseWait.active) return true
  if (s.status === 'running' && s.stepStartedAt != null && !hasReasoningBody(s)) return true
  return false
}

/** 眉标：与规划备忘序号一致（步骤 1、2…）；分步/分支推断仅在下方「思考」折叠区内展示，不在眉标单独写「推断 Todo」 */
const stepEyebrowLabel = (i) => {
  return t('agentTask.stepIndex', { n: i + 1 })
}

/** 执行步骤按工具分子类（摘要/日志消毒） */
const execToolKind = (s) => {
  const fromCall = String(s?.toolCall?.name || '').toLowerCase()
  const t = String(s?.title || '').toLowerCase()
  const blob = `${fromCall} ${t}`
  if (blob.includes('grep')) return 'grep'
  if (blob.includes('modify')) return 'modify'
  if (blob.includes('delete') || blob.includes('删除')) return 'delete'
  if (blob.includes('copy') || blob.includes('复制')) return 'copy'
  if (blob.includes('create')) return 'create'
  if (blob.includes('search')) return 'search'
  if (blob.includes('database')) return 'database'
  if (blob.includes('terminal')) return 'terminal'
  if (blob.includes('cdp') || blob.includes('browser_test')) return 'cdp'
  return 'other'
}

/** 折叠行左侧符号（与历史 tool 卡片图标一致） */
const toolFoldIcon = (s) => {
  const k = execToolKind(s)
  const map = {
    grep: '⌕',
    modify: '✎',
    delete: '🗑',
    copy: '📄',
    create: '＋',
    search: '◉',
    database: '⚗',
    terminal: '▹',
    other: '◇'
  }
  return map[k] || map.other
}

/** 与 chat.stepBatchModify 模板一致：流式落库后不会随采纳重写，需在展示侧切换为已闭环 */
const isBatchModifyAwaitingSandboxSummary = (summary) => {
  const x = String(summary || '')
  if (!x.trim()) return false
  if (/批量修改预览\s*\d+\s*条/.test(x) && (x.includes('沙箱') || x.includes('确认'))) return true
  if (/Batch modify preview/i.test(x) && /sandbox/i.test(x)) return true
  return false
}

const displayStepResultSummary = (s) => {
  const raw = s.resultSummary
  if (raw == null || !String(raw).trim()) return ''
  if (
    props.modifySandboxPending === false &&
    execToolKind(s) === 'modify' &&
    isBatchModifyAwaitingSandboxSummary(raw)
  ) {
    return t('chat.stepBatchModifyDone')
  }
  return String(raw)
}

const sanitizeBatchModifyLineInExecLog = (s, text) => {
  if (props.modifySandboxPending !== false) return text
  if (execToolKind(s) !== 'modify') return text
  let tx = String(text || '')
  const done = t('chat.stepBatchModifyDone')
  tx = tx.replace(/批量修改预览\s*\d+\s*条[^\n]*/g, done)
  tx = tx.replace(/Batch modify preview[^\n]*/gi, (m) => (/sandbox/i.test(m) ? done : m))
  return tx
}

/** 思考可见正文是否已结束流式阶段：未结束前眉标不显示「X 秒」，避免正文还在涨、秒数已跳 */
const thoughtProseStreamFinished = (s) => {
  if (!s) return false
  if (s.thoughtReasoningSnapshot || s.thoughtContentSnapshot) return true
  if (s.thoughtPhaseEndAtMs != null) return true
  const st = s.status
  if (st === 'completed' || st === 'failed' || st === 'skipped' || st === 'error') return true
  return false
}

const thoughtFoldLeftLabel = (s) => {
  void thoughtUiTick.value
  if (!thoughtProseStreamFinished(s) && (s.status === 'running' || s.status === 'pending')) {
    return t('agentTask.thinking')
  }
  return t('agentTask.thought')
}

const thoughtSummaryText = (s) => {
  if (!s) return ''
  if (s.thoughtSummarySnapshot) return sanitizeThoughtSummaryForDisplay(s.thoughtSummarySnapshot)
  return sanitizeThoughtSummaryForDisplay(String(s.thoughtSummaryDraft || '').replace(/\s+/g, ' ').trim())
}

const thoughtSummaryVisible = (s) => {
  const tx = thoughtSummaryText(s)
  if (!tx || isInternalMacroThoughtSummary(tx)) return false
  return tx.length >= 2 && /[\u4e00-\u9fa5A-Za-z0-9]/.test(tx)
}

const thoughtHeaderShimmer = (s) =>
  !!s &&
  !thoughtProseStreamFinished(s) &&
  (s.status === 'running' || s.status === 'pending') &&
  (hasReasoningBody(s) ||
    thoughtBodySubstantive(s) ||
    thoughtSummaryVisible(s) ||
    (s.phaseWait && s.phaseWait.active))

const STEP_SPINNER_DELAY_MS = 300

const stepWallClockElapsedMs = (s, startAt) => {
  if (!s || startAt == null) return 0
  void thoughtUiTick.value
  return Math.max(0, Date.now() - startAt)
}

/** 思考执行中且已超过阈值：右侧转圈（CDP 类工具在 tool 行单独处理） */
const thoughtFoldShowSpinner = (s) => {
  if (!s || thoughtProseStreamFinished(s)) return false
  if (s.status !== 'running' && s.status !== 'pending') return false
  return stepWallClockElapsedMs(s, s.stepStartedAt) >= STEP_SPINNER_DELAY_MS
}

/** 思考结束后右侧显示耗时（沿用简要思考不展示时间的阈值） */
const thoughtFoldDurationRight = (s) => {
  void thoughtUiTick.value
  if (!thoughtProseStreamFinished(s)) return ''
  if (!(thoughtBodySubstantive(s) || hasReasoningBody(s))) return ''
  const timing = s.thoughtTiming
  if (timing && timing.durationMs != null) {
    const thr = timing.briefThresholdMs ?? 800
    if (timing.durationMs < thr) return ''
    return `${(timing.durationMs / 1000).toFixed(1)}s`
  }
  if (s.thoughtPhaseEndAtMs != null && s.stepStartedAt != null) {
    const sec = Math.max(0, (s.thoughtPhaseEndAtMs - s.stepStartedAt) / 1000)
    return `${sec.toFixed(1)}s`
  }
  return ''
}

const toolExecRunning = (s) =>
  !!s && (s.status === 'running' || s.status === 'pending')

const toolFoldDisplayName = (s) => {
  const fromToolCall = s && s.toolCall && typeof s.toolCall === 'object' ? String(s.toolCall.name || '').trim() : ''
  if (fromToolCall) return fromToolCall.length > 40 ? `${fromToolCall.slice(0, 38)}…` : fromToolCall
  const k = execToolKind(s)
  const map = {
    grep: 'grep',
    modify: 'modify',
    delete: 'delete',
    copy: 'copy',
    create: 'create',
    search: 'search',
    database: 'database_query',
    terminal: 'terminal',
    cdp: 'cdp'
  }
  if (map[k]) return map[k]
  const title = String(s.title || '').trim()
  if (title) return title.length > 28 ? `${title.slice(0, 26)}…` : title
  return 'tool'
}

const TOOL_SPINNER_IMMEDIATE_KINDS = new Set(['cdp', 'grep', 'modify', 'delete'])

/** 工具执行中：cdp/grep/modify/delete 立即 spinner；其它工具超过 0.3s 后显示 */
const toolFoldShowSpinner = (s) => {
  if (!toolExecRunning(s)) return false
  if (TOOL_SPINNER_IMMEDIATE_KINDS.has(execToolKind(s))) return true
  const start =
    typeof s.toolExecStartedAt === 'number' ? s.toolExecStartedAt : s.stepStartedAt
  return stepWallClockElapsedMs(s, start) >= STEP_SPINNER_DELAY_MS
}

const toolFoldDuration = (s) => {
  if (!s || toolExecRunning(s)) return ''
  const serverMs =
    typeof s.toolExecDurationMs === 'number' && Number.isFinite(s.toolExecDurationMs)
      ? s.toolExecDurationMs
      : null
  if (serverMs != null && serverMs >= 0) {
    return `${(serverMs / 1000).toFixed(2)}s`
  }

  const total = typeof s.stepDurationMs === 'number' ? s.stepDurationMs : null
  if (total == null || !Number.isFinite(total) || total < 0) return ''

  const stepStartedAt = typeof s.stepStartedAt === 'number' ? s.stepStartedAt : null
  const thoughtEnd = typeof s.thoughtPhaseEndAtMs === 'number' ? s.thoughtPhaseEndAtMs : null
  const toolStart = typeof s.toolExecStartedAt === 'number' ? s.toolExecStartedAt : null
  const stepEndAt = stepStartedAt != null ? stepStartedAt + total : null
  if (toolStart != null && stepEndAt != null && Number.isFinite(stepEndAt)) {
    const toolMs = Math.max(0, stepEndAt - toolStart)
    return `${(toolMs / 1000).toFixed(2)}s`
  }
  if (thoughtEnd != null && stepEndAt != null && Number.isFinite(stepEndAt)) {
    const toolMs = Math.max(0, stepEndAt - thoughtEnd)
    if (toolMs >= 0) return `${(toolMs / 1000).toFixed(2)}s`
  }

  return `${(total / 1000).toFixed(2)}s`
}

const toolExecOpen = (i) => {
  const k = String(i)
  const forced = toolPanelOpen.value[k]
  if (forced !== undefined) return forced
  const s = props.steps[i]
  if (!showToolExecCard(s)) return false
  return toolExecRunning(s)
}

const toggleToolExec = (i) => {
  const k = String(i)
  toolPanelOpen.value = { ...toolPanelOpen.value, [k]: !toolExecOpen(i) }
}

const hasStepThought = (s) => {
  if (s?.macroExecOnly) {
    if (isInternalMacroThoughtSummary(s.thoughtSummarySnapshot || s.thoughtSummaryDraft)) {
      return hasReasoningBody(s) || isPreparingNextStepWait(s)
    }
    return hasReasoningBody(s) || thoughtSummaryVisible(s) || isPreparingNextStepWait(s)
  }
  return (
    hasReasoningBody(s) ||
    !!(s.phaseWait && s.phaseWait.active) ||
    (s.status === 'running' && s.stepStartedAt != null)
  )
}

const thoughtOpen = (i) => {
  const k = String(i)
  const forced = thoughtPanelOpen.value[k]
  if (forced !== undefined) return forced
  const s = props.steps[i]
  if (!s) return false
  // 思考正文已冻结/结束：默认折叠，仅保留标题行（可点开查看）
  if (
    thoughtProseStreamFinished(s) &&
    (thoughtBodySubstantive(s) || hasReasoningBody(s))
  ) {
    return false
  }
  if (s.phaseWait && s.phaseWait.active) return true
  if (s.status === 'running' || s.status === 'pending') return true
  return false
}

const toggleThought = (i) => {
  const k = String(i)
  thoughtPanelOpen.value = { ...thoughtPanelOpen.value, [k]: !thoughtOpen(i) }
}

/** 上一步已完成、本步仍为 pending 时显示（轮次间隙，后端尚未 todo_start） */
const showPendingNextCue = (i) => {
  const cur = props.steps[i]
  if (!cur || cur.status !== 'pending') return false
  if (i === 0) return false
  return props.steps[i - 1]?.status === 'completed'
}

/** 宏路径连续执行：上一步已完成、本步为执行-only，或 phase_wait=preparing_next_step */
const showPreparingNextCue = (i) => {
  const cur = props.steps[i]
  const prev = i > 0 ? props.steps[i - 1] : null
  if (isPreparingNextStepWait(cur)) {
    // grep 完成后 phase_wait 仍挂在已完成步上：衔接提示应出现在下一步前，勿插在本步「思考」上方
    if (cur.status === 'completed' || cur.status === 'skipped' || execPhaseFinished(cur)) {
      return false
    }
    return true
  }
  if (
    prev &&
    isPreparingNextStepWait(prev) &&
    (prev.status === 'completed' || prev.status === 'skipped' || execPhaseFinished(prev))
  ) {
    return true
  }
  return showPendingNextCue(i)
}

const preparingNextCueText = (i) => {
  const cur = props.steps[i]
  const prev = i > 0 ? props.steps[i - 1] : null
  const msg = (cur?.phaseWait?.message || prev?.phaseWait?.message || '').trim()
  return msg || t('agentTask.preparingNextStep')
}

const planLineText = (s, i) => {
  const raw = (s.originalTodo || s.title || t('agentTask.memoFallback', { n: i + 1 })).trim()
  if (raw.length > 120) return raw.slice(0, 118) + '…'
  return raw
}

/** 待执行步骤列表：逐字显示每行（instantPlan 时与 planLineText 一致） */
const planLineDisplay = ref([])
const planTargetStrings = ref([])
let rafPlan = null

const planRowShown = (s, i) => {
  if (props.instantPlan || props.realtimeStream) return planLineText(s, i)
  return planLineDisplay.value[i] ?? ''
}

const runPlanTypewriter = () => {
  if (props.instantPlan || props.realtimeStream) return
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
        // 规划备忘：保持复选框旁“打字机”效果；真正的节奏由 SSE 增量 plan_update 决定
        // 每帧只推进 1 字，避免一次性整块出现
        const n = Math.min(backlog, 1)
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
  planMemoRowModels,
  (rows) => {
    if (props.instantPlan || props.realtimeStream) {
      if (rafPlan != null) {
        cancelAnimationFrame(rafPlan)
        rafPlan = null
      }
      if (!rows?.length) {
        planLineDisplay.value = []
        planTargetStrings.value = []
        return
      }
      planLineDisplay.value = rows.map((s, i) => planLineText(s, i))
      planTargetStrings.value = planLineDisplay.value.slice()
      return
    }
    if (rafPlan != null) {
      cancelAnimationFrame(rafPlan)
      rafPlan = null
    }
    if (!rows?.length) {
      planLineDisplay.value = []
      planTargetStrings.value = []
      return
    }
    const prevTargets = planTargetStrings.value || []
    const newTargets = rows.map((s, i) => planLineText(s, i))
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
  if (props.instantPlan || props.realtimeStream) {
    return sanitizeBatchModifyLineInExecLog(s, execStreamTarget(s))
  }
  return execStreamVisible.value[i] ?? ''
}

/** 日志区：流式过程 + 结果摘要合并为一段纯文本，避免与 detailLog 内「── 结果 ──」重复 */
const execLogMergedText = (s, i) => {
  const streamRaw =
    props.instantPlan || props.realtimeStream
      ? execStreamTarget(s)
      : execStreamShown(s, i) ?? ''
  const stream = sanitizeBatchModifyLineInExecLog(s, streamRaw)
  const sum = displayStepResultSummary(s)
  const streamS = String(stream || '')
  const sumT = String(sum || '').trim()
  if (!sumT) return streamS
  const hasResultSep =
    /─+\s*结果\s*─+/i.test(streamS) || /─+\s*Result\s*─+/i.test(streamS)
  if (hasResultSep || streamS.includes(sumT)) return streamS
  const trimmed = streamS.trimEnd()
  return trimmed ? `${trimmed}\n${sumT}` : sumT
}
const paramsSummaryShown = (s, i) => {
  if (props.instantPlan || props.realtimeStream) return String(s.paramsSummaryDraft || '')
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
const showExecBlock = (s) => !!(streamText(s) || String(displayStepResultSummary(s) || '').trim())
const thoughtStillRunning = (s) =>
  !!(s && s.status === 'running' && hasStepThought(s) && s.thoughtPhaseEndAtMs == null)
const showToolExecCard = (s) =>
  !thoughtStillRunning(s) &&
  (showExecBlock(s) ||
    !!(s.grepNavigation && s.grepNavigation.type === 'multiple' && s.grepNavigation.items?.length) ||
    (s.stepDurationMs != null && s.stepDurationMs >= 0))

const runStreamTypewriters = () => {
  if (props.instantPlan || props.realtimeStream) return
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
          // 流式追赶：积压少时逐字，积压多时加速追赶，避免内容堆积后长时间不可见
          const add = backlog <= 5 ? 1 : Math.min(backlog, Math.max(3, Math.ceil(backlog / 8)))
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
      toolPanelOpen.value = {}
      return
    }
    const n = steps.length
    const prevE = execTargets.value
    const prevR = reasoningTargets.value
    const prevP = paramsTargets.value

    const newE = steps.map((s) => execStreamTarget(s))
    const newR = steps.map((s) => {
      if (s.thoughtReasoningSnapshot) return String(s.thoughtReasoningSnapshot)
      return mergedThoughtReasoningProseFromStep(s)
    })
    const newP = steps.map((s) => String(s.paramsSummaryDraft || ''))

    execTargets.value = newE
    reasoningTargets.value = newR
    paramsTargets.value = newP

    if (props.instantPlan || props.realtimeStream) {
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

const showLogBlock = (s, i = 0) => {
  // 占位首步：Thought 区由 SimpleChatPanel 顶部「...」统一承接；无工具/决策/日志时不渲染空壳
  if (i === 0 && props.hidePrefacePlaceholder) {
    if (!showToolExecCard(s) && !showDecisionBlock(s) && !(s.detailLog && s.detailLog.length)) {
      return false
    }
  }
  return (
    s.status === 'running' ||
    s.status === 'completed' ||
    s.status === 'failed' ||
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
    (s.toolCall &&
      s.toolCall.output &&
      s.toolCall.output !== t('chat.toolExecuting') &&
      s.toolCall.output !== '执行中...') ||
    (s.grepNavigation && s.grepNavigation.items?.length)
  )
}

</script>

<style scoped>
/* 外层不框住「前置思考」，与首轮深度思考同级；步骤正文收在 agent-step-card 内 */
.agent-task-run {
  margin: 6px 0 12px;
  border: none;
  border-radius: 0;
  overflow: visible;
  background: transparent;
}

.agent-step-wrap {
  display: block;
}

.agent-between-steps-cue {
  font-size: 12px;
  color: #94a3b8;
  padding: 6px 2px 8px;
  margin: 0 0 2px;
  letter-spacing: 0.02em;
}

.agent-between-steps-cue--inline {
  margin: 4px 0 8px;
}

/* ReAct Thought：深度思考 reasoning（浅）/ content（亮） */
.agent-thought-deep-reason {
  color: #94a3b8 !important;
  background: rgba(30, 41, 59, 0.35);
  border-radius: 6px;
  padding: 5px 8px !important;
  margin-top: 0 !important;
  margin-bottom: 6px !important;
  border: 1px solid rgba(148, 163, 184, 0.15);
}
.agent-thought-deep-content {
  color: #e2e8f0 !important;
  background: rgba(15, 23, 42, 0.55);
  border-radius: 6px;
  padding: 5px 8px !important;
  margin-top: 0 !important;
  border: 1px solid rgba(148, 163, 184, 0.22);
}

.agent-thought-rich {
  white-space: normal;
}
.agent-thought-stream-plain {
  white-space: pre-wrap;
  margin: 0;
  font-family: inherit;
  font-size: inherit;
  line-height: 1.55;
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
.agent-thought-md :deep(p:empty) {
  display: none;
  margin: 0;
  min-height: 0;
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
  min-height: 22px;
  margin-bottom: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.12);
  border: 1px solid rgba(59, 130, 246, 0.28);
}

.agent-phase-wait--after-thought {
  margin-top: 10px;
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

.agent-plan--after-thought {
  margin-top: 8px;
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

/* SVG 为深色块填色，与 TodoTimeline 一样反相后在暗色条上才看得见 */
.agent-plan-list-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.95;
  filter: invert(1) brightness(0.92);
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

.agent-step-eyebrow {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  padding: 0 2px;
}

.agent-step-eyebrow-bar {
  width: 3px;
  height: 13px;
  border-radius: 2px;
  background: rgba(59, 130, 246, 0.5);
  flex-shrink: 0;
}

.agent-step-eyebrow-text {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.02em;
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
.agent-preface-thought--dots-only {
  margin: 6px 0 0;
  max-width: 100%;
}
.agent-preface-thought--dots-only .agent-phase-wait {
  margin-bottom: 0;
  min-height: auto;
  padding: 0;
  border: none;
  background: transparent;
}

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

/* 思考 / 工具：同一套折叠标题（左图标 + 文案 + 右侧耗时）
   必须显式清掉 button 的 UA / 系统主题底色的，否则会出白底块 */
.agent-step-fold-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 2px 0 2px;
  margin: 0;
  box-sizing: border-box;
  border: none;
  border-radius: 0;
  background: none transparent;
  background-color: transparent;
  box-shadow: none;
  -webkit-appearance: none;
  appearance: none;
  color: inherit;
  font: inherit;
  line-height: inherit;
  cursor: pointer;
  text-align: left;
}
.agent-step-fold-head:disabled {
  cursor: default;
  opacity: 1;
}
.agent-step-fold-head:focus {
  outline: none;
}
.agent-step-fold-head:focus-visible {
  outline: 1px solid rgba(96, 165, 250, 0.45);
  outline-offset: 2px;
}
.agent-step-fold-head--thought:hover:not(:disabled),
.agent-step-fold-head--tool:hover {
  filter: brightness(1.06);
}
.agent-step-fold-head--thought:hover:not(:disabled) {
  background: transparent;
}
.agent-step-fold-thought-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  object-fit: contain;
  display: block;
  opacity: 0.95;
}
.agent-step-fold-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  min-width: 18px;
  height: 18px;
  text-align: center;
  font-size: 14px;
  line-height: 1;
  color: #94a3b8;
  opacity: 0.95;
  font-family: ui-sans-serif, system-ui, sans-serif;
}
.agent-step-fold-head--tool .agent-step-fold-icon {
  color: #7dd3fc;
}
/* 彩色 PNG 工具图标：固定槽位，避免 em 宽度导致折叠行抖动 */
.agent-step-fold-icon-img {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: block;
  object-fit: contain;
  object-position: center;
  opacity: 0.95;
}
/* delete 工具 PNG → 与思考图标同档青蓝（背景色与工具标题一致，形状由 mask 决定） */
.agent-step-fold-icon-tint {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: block;
  background-color: #7dd3fc;
  opacity: 0.95;
  -webkit-mask-size: contain;
  mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  -webkit-mask-position: center;
  mask-position: center;
}
.agent-step-fold-label-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.agent-step-think-summary {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.78rem;
  line-height: 1.35;
  color: rgba(186, 230, 253, 0.82);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.agent-step-fold-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
}
.agent-step-fold-label {
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
}
/* 思考 / 工具标题：同字号、同色（sans，非等宽）；执行中共用 thought-shimmer */
.agent-step-fold-head--thought .agent-step-fold-label,
.agent-step-fold-head--tool .agent-step-fold-label {
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  color: #d4d4d4;
}
/* 执行中：思考与工具共用流动渐变字 */
.agent-step-fold-label--thought-shimmer {
  background: linear-gradient(
    90deg,
    #7dd3fc 0%,
    #a5b4fc 40%,
    #e879f9 70%,
    #7dd3fc 100%
  );
  background-size: 260% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: agentStepFoldShimmer 2.8s linear infinite;
}
.agent-step-fold-duration {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}
.agent-step-fold-spinner {
  margin-left: auto;
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(148, 163, 184, 0.28);
  border-top-color: #7dd3fc;
  border-radius: 50%;
  animation: agentStepFoldSpin 0.72s linear infinite;
}
@keyframes agentStepFoldSpin {
  to {
    transform: rotate(360deg);
  }
}
.agent-step-fold-chevron {
  flex-shrink: 0;
  font-size: 10px;
  color: #64748b;
  opacity: 0.88;
}
.agent-step-fold-chevron--muted {
  opacity: 0.45;
}
@keyframes agentStepFoldShimmer {
  to {
    background-position: 260% center;
  }
}

.agent-preface-thought-feed {
  overflow: visible;
  max-height: none;
  padding: 0 0 6px 24px;
  border: none;
  background: transparent;
}

/* 收紧「思考」标题行与下方正文间距（避免折叠头 padding + feed 留白叠成一大块空白） */
.agent-preface-thought-feed > :first-child {
  margin-top: 0 !important;
}

.agent-preface-thought-feed > .agent-thought-deep-reason:first-child,
.agent-preface-thought-feed > .agent-thought-deep-content:first-child {
  padding-top: 4px !important;
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

/* 工具执行：纯日志样式 */
.agent-tool-exec-log-block {
  margin-top: 4px;
}
.agent-tool-exec-log-block--after-thought {
  margin-top: 4px;
}
.agent-tool-exec-log-body {
  margin: 0;
  padding: 0 0 6px 24px;
}
.agent-tool-exec-log-pre {
  margin: 0;
  padding: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  line-height: 1.55;
  color: #cbd5e1;
  white-space: pre-wrap;
  word-break: break-word;
  background: transparent;
  border: none;
  max-height: 320px;
  overflow: auto;
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

.agent-decision-panel--plain {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
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

.agent-step-planning-inline--plain {
  margin-top: 4px;
  display: inline-block;
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

.agent-decision-observe-rich--plain {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  max-height: none;
  overflow: visible;
}

.agent-step-pre--plain {
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.agent-step-pre--exec {
  color: #f1f5f9;
  background: rgba(15, 23, 42, 0.72);
  border-color: rgba(148, 163, 184, 0.28);
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
  padding-left: 24px;
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

.agent-grep-nav-list-wrap {
  padding: 4px 8px 8px;
}
.agent-grep-nav-list-shell {
  position: relative;
}
.agent-grep-nav-list-shell.is-collapsed .agent-grep-nav-list-inner {
  max-height: 120px;
  overflow: hidden;
}
.agent-grep-nav-list-inner {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.agent-grep-nav-list-fade {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 40px;
  pointer-events: none;
  background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.92));
}
.agent-grep-nav-expand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-top: 6px;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
  cursor: pointer;
  transition: background 0.15s ease;
}
.agent-grep-nav-expand:hover {
  background: rgba(59, 130, 246, 0.22);
}
.agent-grep-nav-expand-chevron {
  font-size: 10px;
  opacity: 0.9;
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
