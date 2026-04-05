/**
 * ReAct SSE 协议 v1 — UI 状态补丁（与后端 type: plan | step | tail 对齐）
 */
import {
  mergeMessageThinkDraftsIntoReactStepZero,
  maybeRevealPlanMemoAfterThink
} from './applyReactThinkSSEStepEvent.js'
import { freezeThoughtSnapshotForStep } from './thoughtSnapshot.js'

export function applyPlanPayloadV1(aiMessage, payload, buildReactStepsFromTodoStrings) {
  const pl = payload || {}
  // 当 steps 为空或显式 suppress 时，不显示规划备忘
  if (!Array.isArray(pl.steps) || !pl.steps.length) {
    aiMessage._planMemoRevealReady = true
    aiMessage.reactPlanPanelSuppressed = true
    aiMessage.reactPlanSteps = []
    return
  }
  const todoStrings = pl.steps.map((s) =>
    typeof s === 'string' ? s : (s && (s.name || s.title || s.text)) || ''
  )
  if (pl.suppress_plan_ui) {
    // suppress_plan_ui=true: 强制隐藏规划备忘，不让 maybeRevealPlanMemoAfterThink 揭示
    aiMessage.reactPlanPanelSuppressed = true
    aiMessage._planMemoRevealReady = true  // 直接标记为已就绪，不再揭示
    aiMessage._deferPlanMemoUntilThink = false  // 不等待 think 正文
    aiMessage.reactPlanSteps = []  // 清空步骤，避免显示
    if (pl.mode != null) aiMessage.reactTaskMode = pl.mode
    if (pl.reason != null && pl.reason !== '') aiMessage.planUpdateReason = pl.reason
    if (pl.react_phase) aiMessage.lastReactPhase = pl.react_phase
    return
  }
  // 非 suppress：显示规划备忘
  aiMessage.reactPlanPanelSuppressed = false
  aiMessage.reactPlanSteps = pl.steps
  if (pl.overview_only != null) aiMessage.planOverviewOnly = !!pl.overview_only
  if (pl.mode != null) aiMessage.reactTaskMode = pl.mode
  if (pl.reason != null && pl.reason !== '') aiMessage.planUpdateReason = pl.reason
  if (pl.react_phase) aiMessage.lastReactPhase = pl.react_phase
  if (aiMessage._placeholderSteps || todoStrings.length > (aiMessage.steps || []).length) {
    aiMessage.steps = buildReactStepsFromTodoStrings(todoStrings)
    aiMessage._placeholderSteps = false
    mergeMessageThinkDraftsIntoReactStepZero(aiMessage)
  }
  maybeRevealPlanMemoAfterThink(aiMessage)
  if (!aiMessage._planMemoRevealReady && !aiMessage._deferPlanMemoUntilThink) {
    aiMessage._planMemoRevealReady = true
  }
}

export function applyStepPayloadV1(aiMessage, payload) {
  const p = payload || {}
  const si = Number(p.index)
  if (!Number.isFinite(si) || !Array.isArray(aiMessage.steps) || !aiMessage.steps[si]) return
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
  if (chunk.react_phase) aiMessage.lastReactPhase = chunk.react_phase
  if (
    aiMessage._planMemoRevealReady === false &&
    Array.isArray(aiMessage.steps) &&
    aiMessage.steps.length > 0
  ) {
    aiMessage._planMemoRevealReady = true
    aiMessage.reactPlanPanelSuppressed = false
  }
}
