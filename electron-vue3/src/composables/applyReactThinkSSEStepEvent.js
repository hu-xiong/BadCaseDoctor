import { i18n } from '../i18n/index.js'

/** 是否已有可展示的思考正文（与 AgentTaskRun thoughtBodySubstantive 对齐） */
function thoughtStepHasSubstantiveProse(st, aiMessage) {
  const m = (t) => {
    const u = String(t || '').replace(/\u200b/g, '').trim()
    return u.length >= 2 && /[\u4e00-\u9fa5A-Za-z0-9]/.test(u)
  }
  if (st) {
    if (m(st.thoughtReasoningDraft)) return true
    const rawC = String(st.thoughtContentDraft || '')
    if (m(rawC)) return true
    const merged = [st.agentThoughtDraft, st.reasoningDecideDraft, st.reasoningStepDraft]
      .filter(Boolean)
      .join('\n')
    if (m(merged)) return true
  }
  if (aiMessage) {
    if (m(aiMessage.thinkReasoningDraft)) return true
    if (m(aiMessage.thinkContentDraft)) return true
    if (m(aiMessage.reasoningContent)) return true
  }
  return false
}

/** 进入决策块时冻结「思考」墙钟 */
function freezeThoughtPhaseEndForActionXmlWait(st, aiMessage) {
  if (!st || st.thoughtPhaseEndAtMs != null || st.stepStartedAt == null) return
  if (!thoughtStepHasSubstantiveProse(st, aiMessage)) return
  st.thoughtPhaseEndAtMs = Date.now()
}

/**
 * 后端已将 XML 转换为语义标记，前端直接透传即可
 * 保留此函数接口以兼容旧代码，未来可在此添加其他过滤逻辑
 */
function appendUnifiedFilteredThinkPiece(aiMessage, j, piece) {
  // 后端 unified_think_stream_sanitize 已处理 XML 转换，直接返回原文
  return typeof piece === 'string' ? piece : ''
}

/** plan 轨 todo_list XML：reasoning 已出正文后冻结墙钟并显示等待点（无 <decision> 过滤器时） */
function maybeFreezeThoughtForTodoXmlTail(aiMessage) {
  const tc = String(aiMessage.thinkContentDraft || '').trim()
  if (!tc || !/<todo_list\b/i.test(tc)) return
  const trMsg = String(aiMessage.thinkReasoningDraft || '').replace(/\u200b/g, '').trim()
  const msgProseOk =
    trMsg.length >= 2 && /[\u4e00-\u9fa5A-Za-z0-9]/.test(trMsg)
  const steps = aiMessage.steps || []
  const now = Date.now()
  for (const st of steps) {
    if (st.status !== 'running' || st.stepStartedAt == null) continue
    if (st.thoughtPhaseEndAtMs != null) continue
    const str = String(st.thoughtReasoningDraft || '').replace(/\u200b/g, '').trim()
    const stepProseOk = str.length >= 2 && /[\u4e00-\u9fa5A-Za-z0-9]/.test(str)
    if (!msgProseOk && !stepProseOk) continue
    st.thoughtPhaseEndAtMs = now
    if (!st.phaseWait?.active) {
      st.phaseWait = {
        active: true,
        kind: 'plan_xml_stream',
        message: i18n.global.t('chat.phaseWaitParsingAction')
      }
    }
  }
}

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
  const hasPlan = Array.isArray(aiMessage.reactPlanSteps) && aiMessage.reactPlanSteps.length > 0
  if (hasPlan) {
    aiMessage.reactPlanPanelSuppressed = false
  }
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
  const multiStep = Array.isArray(aiMessage.steps) && aiMessage.steps.length > 1
  /** 计划到达后 agent_thought 只写 step.agentThoughtDraft，message.thinkReasoningDraft 不再变长；勿用短 tr 覆盖已 merge 的长正文 */
  const mergeThoughtReasoningDraft = (next) => {
    const n = String(next || '')
    if (!n.trim()) return
    const cur = String(st.thoughtReasoningDraft || '')
    if (!cur.trim() || n.length >= cur.length) st.thoughtReasoningDraft = n
  }
  if (aiMessage._placeholderSteps) {
    mergeThoughtReasoningDraft(tr)
    if (tc) st.thoughtContentDraft = tc
    if (!tr && !tc && rc) mergeThoughtReasoningDraft(rc)
  } else if ((aiMessage.lastReactPhase === 'think' || aiMessage.lastReactPhase === 'observe' || aiMessage.lastReactPhase === 'decide') && !multiStep) {
    // 修复：统一流的所有思考阶段（think/observe/decide）都同步到 steps[0]
    mergeThoughtReasoningDraft(tr)
    if (tc) st.thoughtContentDraft = tc
    if (!String(tr).trim() && !String(tc).trim() && String(rc).trim()) mergeThoughtReasoningDraft(rc)
  }
  const merged = (tr || tc || rc).replace(/\u200b/g, '').trim()
  const pwk = String(st.phaseWait?.kind || '')
  if (merged.length > 0 && pwk !== 'unified_action_xml' && pwk !== 'plan_xml_stream') {
    st.phaseWait = null
  }
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

      let pieceVisible = typeof piece === 'string' ? piece : ''
      if (typeof piece === 'string' && piece && isThink) {
        pieceVisible = appendUnifiedFilteredThinkPiece(aiMessage, j, piece)
      }

      if (typeof piece === 'string' && piece && isThink) {
        aiMessage.hadAgentThinkPhase = true
        aiMessage._reasoningPhaseLive = true
        if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
        // 无论 j 是否为 null，都更新 thinkReasoningDraft 以确保前端实时显示
        aiMessage.thinkReasoningDraft = (aiMessage.thinkReasoningDraft || '') + pieceVisible
        aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
        
        // 如果没有 steps，创建占位 step（统一流首轮）
        if ((!aiMessage.steps || aiMessage.steps.length === 0) && ctx.ensureThinkPlaceholder) {
          ctx.ensureThinkPlaceholder(aiMessage)
        }
        
        // 同步到 steps[0]（如果存在）
        syncPlaceholderStepThought(aiMessage)
        
        scheduleReasoningTypewriter(aiMessage)
      }
      // 更新 lastReactPhase 以便 syncPlaceholderStepThought 正确同步
      if (stepEvent.react_phase) {
        aiMessage.lastReactPhase = stepEvent.react_phase
      }
      if (j != null && aiMessage.steps[j] && typeof piece === 'string' && piece) {
        const st = aiMessage.steps[j]
        st.agentThoughtDraft = (st.agentThoughtDraft || '') + pieceVisible
        const vis = pieceVisible.replace(/[\u200B-\u200D\uFEFF\u2060]/g, '').trim()
        if (vis.length > 0 && st.phaseWait?.active) {
          const pk = String(st.phaseWait.kind || '')
          if (pk !== 'unified_action_xml') {
            st.phaseWait = null
          }
        }
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
        const kind = stepEvent.kind != null ? String(stepEvent.kind) : ''
        if (stepEvent.active) {
          // unified_round_think：等待模型首 token 前，勿把「开始等待」当成思考已结束，否则眉标会显示 0.0 秒
          if (
            kind !== 'unified_round_think' &&
            st.thoughtPhaseEndAtMs == null &&
            st.stepStartedAt != null
          ) {
            st.thoughtPhaseEndAtMs = Date.now()
          }
          st.phaseWait = {
            active: true,
            kind,
            message: stepEvent.message != null ? String(stepEvent.message) : ''
          }
        } else {
          st.phaseWait = null
          if (kind === 'unified_round_think') {
            st.thoughtPhaseEndAtMs = Date.now()
          }
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
        let j = resolveStreamStepIndex(stepEvent.index, aiMessage.steps)
        if (
          j == null &&
          Array.isArray(aiMessage.steps) &&
          aiMessage.steps.length === 1 &&
          (stepEvent.index === 0 || stepEvent.index === '0')
        ) {
          j = 0
        }
        const rp = stepEvent.react_phase
        const sc = stepEvent.stream_channel || 'reasoning'
        const isThink =
          !rp || rp === 'think' || (typeof sseIsReactThinkPhase === 'function' && sseIsReactThinkPhase(rp))
        /** 与 isThink 对齐：缺省 react_phase 时也应写入 thinkReasoningDraft，勿只写 reasoningContent（否则 plan 到达后不同步到 steps[0]，Thought 空白） */
        const inThinkDraftPhase =
          typeof sseIsReactThinkPhase === 'function' ? sseIsReactThinkPhase(rp) : !rp || rp === 'think'
        const pieceVisible = isThink ? appendUnifiedFilteredThinkPiece(aiMessage, j, piece) : piece

        if (sseIsReactThinkPhase(stepEvent.react_phase)) aiMessage.hadAgentThinkPhase = true
        if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
        aiMessage._reasoningPhaseLive = true
        if (inThinkDraftPhase && sc === 'reasoning') {
          aiMessage.thinkReasoningDraft = (aiMessage.thinkReasoningDraft || '') + pieceVisible
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
          scheduleReasoningTypewriter(aiMessage)
          // 有 reasoning 时自动展开（避免“最后隐藏/折叠导致看不到”）
          try {
            const vis = String(pieceVisible || '').replace(/[\u200B-\u200D\uFEFF\u2060]/g, '').trim()
            if (vis && aiMessage.thoughtCollapsed === true) aiMessage.thoughtCollapsed = false
          } catch {
            // ignore
          }
        } else if (inThinkDraftPhase && sc === 'content') {
          aiMessage.thinkContentDraft = (aiMessage.thinkContentDraft || '') + pieceVisible
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
          scheduleReasoningTypewriter(aiMessage)
        } else {
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
          scheduleReasoningTypewriter(aiMessage)
        }
        if (stepEvent.react_phase) aiMessage.lastReactPhase = stepEvent.react_phase
        else if (inThinkDraftPhase) aiMessage.lastReactPhase = 'think'
        logReactThinkStepDetail(stepEvent, aiMessage)
        if (piece !== '' && ctx.ensureThinkPlaceholder) {
          const vis = pieceVisible.replace(/[\u200B-\u200D\uFEFF\u2060]/g, '').trim()
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
        maybeFreezeThoughtForTodoXmlTail(aiMessage)
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
  const pwk0 = String(s0.phaseWait?.kind || '')
  if (merged.length > 0 && pwk0 !== 'unified_action_xml' && pwk0 !== 'plan_xml_stream') {
    s0.phaseWait = null
  }
}
