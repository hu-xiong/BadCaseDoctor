/**
 * 后端 plan_init 带 suppress 时 _planMemoRevealReady 仍为 false：仅在 THINK 草稿有足够正文后再揭示「规划备忘」。
 */
export function maybeRevealPlanMemoAfterThink(aiMessage) {
  if (!aiMessage || aiMessage._planMemoRevealReady) return
  const tr = String(aiMessage.thinkReasoningDraft || '')
    .replace(/\u200b/g, '')
    .trim()
  const tc = String(aiMessage.thinkContentDraft || '')
    .replace(/\u200b/g, '')
    .trim()
  const rc = String(aiMessage.reasoningContent || '')
    .replace(/\u200b/g, '')
    .trim()
  const merged = tr || tc || rc
  if (merged.length < 2) return
  if (!/[\u4e00-\u9fa5A-Za-z0-9]/.test(merged)) return
  aiMessage._planMemoRevealReady = true
  aiMessage.reactPlanPanelSuppressed = false
}

/**
 * hello/phase 挂的占位 step：THINK 流只写在 aiMessage，AgentTaskRun 读的是 step.thought*，不同步则长时间只有「...」。
 * 将首轮思考镜像到 steps[0]，并清 phaseWait，避免与顶部 loading 重复多段等待动画。
 */
function syncPlaceholderStepThought(aiMessage) {
  if (!aiMessage?.steps?.[0]) return
  const st = aiMessage.steps[0]
  const tr = aiMessage.thinkReasoningDraft || ''
  const tc = aiMessage.thinkContentDraft || ''
  const rc = (aiMessage.reasoningContent || '').replace(/\u200b/g, '')
  if (aiMessage._placeholderSteps) {
    if (tr) st.thoughtReasoningDraft = tr
    if (tc) st.thoughtContentDraft = tc
    if (!tr && !tc && rc) st.thoughtReasoningDraft = rc
  } else if (aiMessage.lastReactPhase === 'think') {
    if (tr) st.thoughtReasoningDraft = tr
    if (tc) st.thoughtContentDraft = tc
    if (!String(tr).trim() && !String(tc).trim() && String(rc).trim()) st.thoughtReasoningDraft = rc
  }
  const merged = (tr || tc || rc).replace(/\u200b/g, '').trim()
  if (merged.length > 0) st.phaseWait = null
  maybeRevealPlanMemoAfterThink(aiMessage)
}

/**
 * ReAct THINK 阶段流式 step 事件（reasoning / todos_stream 中与 Thought 合并的逻辑等）。
 * 返回 true 表示已消费该事件。
 */
export function applyReactThinkSSEStepEvent(aiMessage, stepEvent, ctx) {
  const {
    resolveStreamStepIndex,
    scheduleReasoningTypewriter,
    scheduleTodosStreamTypewriter,
    sseIsReactThinkPhase,
    logReactThinkStepDetail
  } = ctx

  switch (stepEvent.event) {
    case 'reasoning_timing': {
      const seg = stepEvent.segment
      if (seg === 'think') {
        if (stepEvent.duration_ms != null) aiMessage.reasoningUiDurationMs = Number(stepEvent.duration_ms)
        if (stepEvent.kind) aiMessage.reasoningUiKind = stepEvent.kind
        if (stepEvent.brief_threshold_ms != null) aiMessage.reasoningBriefThresholdMs = Number(stepEvent.brief_threshold_ms)
      } else if ((seg === 'decide' || seg === 'observe') && stepEvent.index != null) {
        const j = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
        if (j != null && aiMessage.steps[j]) {
          const st = aiMessage.steps[j]
          const add = stepEvent.duration_ms != null ? Number(stepEvent.duration_ms) : 0
          const prev = st.thoughtTiming
          let totalMs = add
          if (seg === 'observe' && prev && prev.segment === 'decide' && prev.durationMs != null) {
            totalMs = Number(prev.durationMs) + add
          }
          st.thoughtTiming = {
            durationMs: totalMs,
            kind: stepEvent.kind || null,
            segment: seg,
            briefThresholdMs: stepEvent.brief_threshold_ms != null ? Number(stepEvent.brief_threshold_ms) : 800
          }
        }
      }
      return true
    }
    case 'agent_thought': {
      let j = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
      if (
        j == null &&
        Array.isArray(aiMessage.steps) &&
        aiMessage.steps.length === 1 &&
        (stepEvent.index === 0 || stepEvent.index === '0')
      ) {
        j = 0
      }
      const piece = stepEvent.delta
      const rp = stepEvent.react_phase
      const isThink =
        !rp || rp === 'think' || (typeof sseIsReactThinkPhase === 'function' && sseIsReactThinkPhase(rp))
      if (typeof piece === 'string' && piece && isThink) {
        aiMessage.hadAgentThinkPhase = true
        aiMessage._reasoningPhaseLive = true
        if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
        aiMessage.thinkReasoningDraft = (aiMessage.thinkReasoningDraft || '') + piece
        aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + piece
        scheduleReasoningTypewriter(aiMessage)
        syncPlaceholderStepThought(aiMessage)
      }
      if (j != null && aiMessage.steps[j] && typeof piece === 'string' && piece) {
        const st = aiMessage.steps[j]
        st.agentThoughtDraft = (st.agentThoughtDraft || '') + piece
      }
      return true
    }
    case 'reasoning_step': {
      const j = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
      if (j != null && aiMessage.steps[j] && typeof stepEvent.content === 'string') {
        const st = aiMessage.steps[j]
        const seg = stepEvent.segment
        const piece = stepEvent.content
        if (seg === 'decide') {
          st.reasoningDecideDraft = (st.reasoningDecideDraft || '') + piece
        } else if (seg !== 'observe') {
          st.reasoningStepDraft = (st.reasoningStepDraft || '') + piece
        }
        if (seg !== 'observe') {
          st.thoughtReasoningDraft = (st.thoughtReasoningDraft || '') + piece
        }
      }
      return true
    }
    case 'phase_wait': {
      const j = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
      if (j != null && aiMessage.steps[j]) {
        const st = aiMessage.steps[j]
        if (stepEvent.active) {
          if (st.thoughtPhaseEndAtMs == null && st.stepStartedAt != null) {
            st.thoughtPhaseEndAtMs = Date.now()
          }
          st.phaseWait = {
            active: true,
            kind: stepEvent.kind || '',
            message: stepEvent.message != null ? String(stepEvent.message) : ''
          }
        } else {
          st.phaseWait = null
        }
      }
      return true
    }
    case 'thought_content_step': {
      const j = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
      const piece = stepEvent.delta
      if (j != null && aiMessage.steps[j] && typeof piece === 'string' && piece) {
        const st = aiMessage.steps[j]
        st.thoughtContentDraft = (st.thoughtContentDraft || '') + piece
      }
      return true
    }
    case 'reasoning': {
      let piece = stepEvent.content
      if (piece == null || piece === undefined) piece = stepEvent.data
      if (typeof piece !== 'string') piece = ''
      if (piece !== '') {
        if (sseIsReactThinkPhase(stepEvent.react_phase)) aiMessage.hadAgentThinkPhase = true
        if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
        aiMessage._reasoningPhaseLive = true
        const rp = stepEvent.react_phase
        const sc = stepEvent.stream_channel
        if (rp === 'think' && sc === 'reasoning') {
          aiMessage.thinkReasoningDraft = (aiMessage.thinkReasoningDraft || '') + piece
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + piece
          scheduleReasoningTypewriter(aiMessage)
        } else if (rp === 'think' && sc === 'content') {
          aiMessage.thinkContentDraft = (aiMessage.thinkContentDraft || '') + piece
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + piece
          scheduleReasoningTypewriter(aiMessage)
        } else {
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + piece
          scheduleReasoningTypewriter(aiMessage)
        }
        if (stepEvent.react_phase) aiMessage.lastReactPhase = stepEvent.react_phase
        logReactThinkStepDetail(stepEvent, aiMessage)
        if (piece !== '' && ctx.ensureThinkPlaceholder) {
          const vis = piece.replace(/[\u200B-\u200D\uFEFF\u2060]/g, '').trim()
          if (vis.length > 0) ctx.ensureThinkPlaceholder(aiMessage)
        }
        syncPlaceholderStepThought(aiMessage)
      }
      return true
    }
    case 'todos_stream': {
      const piece = stepEvent.delta
      if (typeof piece === 'string' && piece) {
        if (sseIsReactThinkPhase(stepEvent.react_phase)) {
          aiMessage.hadAgentThinkPhase = true
          aiMessage._reasoningPhaseLive = true
        }
        aiMessage.todosStreamDraft = (aiMessage.todosStreamDraft || '') + piece
        scheduleTodosStreamTypewriter(aiMessage)
        if (!aiMessage.steps || aiMessage.steps.length === 0) {
          const rp = stepEvent.react_phase
          const sc = stepEvent.stream_channel
          aiMessage._thinkTodoMergedIntoReasoning = true
          if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
          aiMessage._reasoningPhaseLive = true
          if (rp === 'think' && sc === 'content') {
            aiMessage.thinkContentDraft = (aiMessage.thinkContentDraft || '') + piece
            aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + piece
            scheduleReasoningTypewriter(aiMessage)
          } else {
            aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + piece
            scheduleReasoningTypewriter(aiMessage)
          }
        }
        if (stepEvent.react_phase) aiMessage.lastReactPhase = stepEvent.react_phase
        logReactThinkStepDetail(stepEvent, aiMessage)
        if (typeof piece === 'string' && piece && ctx.ensureThinkPlaceholder) {
          ctx.ensureThinkPlaceholder(aiMessage)
        }
        syncPlaceholderStepThought(aiMessage)
      }
      return true
    }
    default:
      return false
  }
}

/**
 * THINK 轨写在 aiMessage 上的草稿，在 todos / plan 建成正式 steps 后并入 steps[0]，
 * 与 AgentTaskRun「先思考、后规划备忘」的 DOM 顺序一致，避免只有 message 有正文而 step0 空白。
 */
export function mergeMessageThinkDraftsIntoReactStepZero(aiMessage) {
  if (!aiMessage?.steps?.[0]) return
  const s0 = aiMessage.steps[0]
  const tr = aiMessage.thinkReasoningDraft || ''
  const tc = aiMessage.thinkContentDraft || ''
  const rc = (aiMessage.reasoningContent || '').replace(/\u200b/g, '')
  if (tr) s0.thoughtReasoningDraft = tr
  if (tc) s0.thoughtContentDraft = tc
  if (!String(tr).trim() && !String(tc).trim() && String(rc).trim()) s0.thoughtReasoningDraft = rc
  const merged = (tr || tc || rc).replace(/\u200b/g, '').trim()
  if (merged.length > 0) s0.phaseWait = null
}
