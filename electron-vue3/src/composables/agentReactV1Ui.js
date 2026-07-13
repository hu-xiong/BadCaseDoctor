/**
 * ReAct SSE 协议 v1 — UI 状态补丁（与后端 type: plan | step | tail 对齐）
 */
import {
  finalizeMessageFirstThinkStream,
  mergeMessageThinkDraftsIntoReactStepZero,
  maybeRevealPlanMemoAfterThink
} from './applyReactThinkSSEStepEvent.js'
import { freezeThoughtSnapshotForStep } from './thoughtSnapshot.js'

/**
 * todos / todos_partial 用正式步骤替换占位 steps 时，把占位 step0 上的思考墙钟与过滤器状态拷到新 step0，
 * 避免收到计划后「思考计时从 0 再起」或统一流 phaseWait/_unifiedThoughtFs 丢失。
 * @param {unknown[]} prevSteps
 * @param {unknown[]} nextSteps
 * @param {boolean} hadPlaceholder
 */
export function mergeBuiltStepsPreservingPlaceholderThinkClock(prevSteps, nextSteps, hadPlaceholder) {
  if (!hadPlaceholder || !Array.isArray(prevSteps) || !Array.isArray(nextSteps)) return
  const p0 = prevSteps[0]
  const n0 = nextSteps[0]
  if (!p0 || !n0) return

  if (p0.stepStartedAt != null) n0.stepStartedAt = p0.stepStartedAt
  if (p0.thoughtPhaseEndAtMs != null) n0.thoughtPhaseEndAtMs = p0.thoughtPhaseEndAtMs
  if (p0.thoughtTiming != null) n0.thoughtTiming = p0.thoughtTiming
  if (p0.stepDurationMs != null) n0.stepDurationMs = p0.stepDurationMs
  if (p0._unifiedThoughtFs != null) n0._unifiedThoughtFs = p0._unifiedThoughtFs

  if (p0.phaseWait?.active) {
    n0.phaseWait = p0.phaseWait
  }

  if (p0.thoughtReasoningDraft && !n0.thoughtReasoningDraft) n0.thoughtReasoningDraft = p0.thoughtReasoningDraft
  if (p0.thoughtContentDraft && !n0.thoughtContentDraft) n0.thoughtContentDraft = p0.thoughtContentDraft
  if (p0.agentThoughtDraft && !n0.agentThoughtDraft) n0.agentThoughtDraft = p0.agentThoughtDraft
}

/** plan / plan_init 用正式步骤替换占位 steps 时，保留占位 step0 的思考墙钟与草稿 */
function replacePlanTodoStepsPreservingThinkClock(aiMessage, todoStrings, buildReactStepsFromTodoStrings) {
  const hadPh = !!aiMessage._placeholderSteps
  const prevSteps = aiMessage.steps
  aiMessage.steps = buildReactStepsFromTodoStrings(todoStrings)
  aiMessage._placeholderSteps = false
  mergeBuiltStepsPreservingPlaceholderThinkClock(prevSteps, aiMessage.steps, hadPh)
  mergeMessageThinkDraftsIntoReactStepZero(aiMessage)
  finalizeMessageFirstThinkStream(aiMessage)
}

export function applyPlanPayloadV1(aiMessage, payload, buildReactStepsFromTodoStrings) {
  const pl = payload || {}
  // 无 steps = 未下发计划：不写入 reactPlanSteps，规划备忘不出现（不靠 suppress 硬藏）
  if (!Array.isArray(pl.steps) || !pl.steps.length) {
    aiMessage._planMemoRevealReady = true
    return
  }
  const todoStrings = pl.steps.map((s) =>
    typeof s === 'string' ? s : (s && (s.name || s.title || s.text)) || ''
  )
  /** 终端子 Agent 续跑：同一条助手消息上追加新计划行，SSE 步骤下标仍从 0 起，由 _reactStreamStepBase 偏移 */
  if (
    aiMessage._terminalMergeContinue === true &&
    Array.isArray(aiMessage.steps) &&
    aiMessage.steps.length > 0
  ) {
    const newSteps = buildReactStepsFromTodoStrings(todoStrings)
    aiMessage.steps = [...aiMessage.steps, ...newSteps]
    aiMessage._placeholderSteps = false
    mergeMessageThinkDraftsIntoReactStepZero(aiMessage)
    const prevPlan = Array.isArray(aiMessage.reactPlanSteps) ? aiMessage.reactPlanSteps : []
    aiMessage.reactPlanSteps = [...prevPlan, ...pl.steps]
    if (pl.suppress_plan_ui) {
      aiMessage.reactPlanPanelSuppressed = true
      aiMessage._deferPlanMemoUntilThink = true
    } else {
      aiMessage.reactPlanPanelSuppressed = false
    }
    if (pl.overview_only != null) aiMessage.planOverviewOnly = !!pl.overview_only
    if (pl.mode != null) aiMessage.reactTaskMode = pl.mode
    if (pl.reason != null && pl.reason !== '') aiMessage.planUpdateReason = pl.reason
    if (pl.react_phase) aiMessage.lastReactPhase = pl.react_phase
    maybeRevealPlanMemoAfterThink(aiMessage)
    if (!pl.suppress_plan_ui && !aiMessage._planMemoRevealReady && !aiMessage._deferPlanMemoUntilThink) {
      aiMessage._planMemoRevealReady = true
    }
    return
  }
  if (pl.suppress_plan_ui) {
    aiMessage.reactPlanPanelSuppressed = true
    aiMessage._deferPlanMemoUntilThink = true
    aiMessage.reactPlanSteps = pl.steps
    if (pl.overview_only != null) aiMessage.planOverviewOnly = !!pl.overview_only
    if (pl.mode != null) aiMessage.reactTaskMode = pl.mode
    if (pl.reason != null && pl.reason !== '') aiMessage.planUpdateReason = pl.reason
    if (pl.react_phase) aiMessage.lastReactPhase = pl.react_phase
    if (aiMessage._placeholderSteps || todoStrings.length > (aiMessage.steps || []).length) {
      replacePlanTodoStepsPreservingThinkClock(aiMessage, todoStrings, buildReactStepsFromTodoStrings)
    }
    maybeRevealPlanMemoAfterThink(aiMessage)
    return
  }
  // 非 suppress：旧版首包即展示；若曾 defer（plan_init 带 suppress），须等 THINK 正文再揭示
  aiMessage.reactPlanPanelSuppressed = false
  aiMessage.reactPlanSteps = pl.steps
  if (pl.overview_only != null) aiMessage.planOverviewOnly = !!pl.overview_only
  if (pl.mode != null) aiMessage.reactTaskMode = pl.mode
  if (pl.reason != null && pl.reason !== '') aiMessage.planUpdateReason = pl.reason
  if (pl.react_phase) aiMessage.lastReactPhase = pl.react_phase
  if (aiMessage._placeholderSteps || todoStrings.length > (aiMessage.steps || []).length) {
    replacePlanTodoStepsPreservingThinkClock(aiMessage, todoStrings, buildReactStepsFromTodoStrings)
  }
  maybeRevealPlanMemoAfterThink(aiMessage)
  if (!aiMessage._planMemoRevealReady && !aiMessage._deferPlanMemoUntilThink) {
    aiMessage._planMemoRevealReady = true
  }
}

export function applyStepPayloadV1(aiMessage, payload) {
  const p = payload || {}
  const base = Number(aiMessage._reactStreamStepBase || 0)
  const rel = Number(p.index)
  const si = base + rel
  if (!Number.isFinite(rel) || !Number.isFinite(si) || !Array.isArray(aiMessage.steps) || !aiMessage.steps[si])
    return
  const map = { 0: 'pending', 1: 'running', 2: 'completed', 3: 'skipped' }
  const st = map[p.s]
  if (st) {
    const row = aiMessage.steps[si]
    if (st === 'completed' || st === 'skipped') freezeThoughtSnapshotForStep(row)
    row.status = st
  }
  if (p.react_phase) aiMessage.lastReactPhase = p.react_phase
}

export function applyTailPayloadV1(aiMessage, payload) {
  const chunk = payload || {}
  aiMessage.reactMainLoopFinished = true
  if (aiMessage.understanding === '...') aiMessage.understanding = ''
  aiMessage.reactFinishedMeta = {
    mode: chunk.mode,
    finished: chunk.finished,
    steps_count: chunk.steps_count,
    duration: chunk.duration,
    thinking_time: chunk.thinking_time,
    observations: chunk.observations,
    plan_snapshot: chunk.plan_snapshot,
    t: Date.now()
  }
  // 同时更新 agentResult，供「总结 Xs」等 UI 显示使用
  if (chunk.duration != null) {
    aiMessage.agentResult.execution_time = chunk.duration
  }
  if (chunk.thinking_time != null) {
    aiMessage.agentResult.thinking_time = chunk.thinking_time
  }
  if (chunk.steps_count != null) {
    aiMessage.agentResult.steps_count = chunk.steps_count
  }
  if (chunk.react_phase) aiMessage.lastReactPhase = chunk.react_phase
  if (
    aiMessage._planMemoRevealReady === false &&
    Array.isArray(aiMessage.steps) &&
    aiMessage.steps.length > 0
  ) {
    aiMessage._planMemoRevealReady = true
    if (Array.isArray(aiMessage.reactPlanSteps) && aiMessage.reactPlanSteps.length > 0) {
      aiMessage.reactPlanPanelSuppressed = false
    }
  }
}
