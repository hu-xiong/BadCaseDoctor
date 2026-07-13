import { i18n } from '../i18n/index.js'
import { stripReasoningChannelArtifacts } from '../utils/stripReasoningChannelArtifacts.js'
import { freezeThoughtSnapshotForStep } from './thoughtSnapshot.js'

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

/**
 * THINK / think_summary 绑定步骤：优先 step_id；round_idx 常大于 plan 步时回落到首个未执行工具步。
 */
function resolvePlanAlignedThinkStepIndex(steps, j) {
  if (j == null || !Array.isArray(steps) || !steps[j]) return j
  const st = steps[j]
  if (!st.toolCall && st.status !== 'completed') return j
  const pending = steps.findIndex(
    (s) => s && (s.status === 'running' || s.status === 'pending') && !s.toolCall
  )
  if (pending >= 0 && pending < j) return pending
  return j
}

function resolveThinkTargetStep(aiMessage, stepEvent, resolveStreamStepIndex) {
  const steps = aiMessage?.steps
  if (!Array.isArray(steps) || !steps.length) return { j: null, st: null }
  const ev = stepEvent && typeof stepEvent === 'object' ? stepEvent : { index: stepEvent }
  let j = null
  const sid = ev.step_id ?? ev.stepId
  if (sid != null && sid !== '') {
    const n = Number(sid)
    if (Number.isFinite(n) && n >= 1 && steps[n - 1]) j = n - 1
  }
  if (j == null) j = resolveStreamStepIndex(ev.index, steps)
  if (j != null && steps[j]) {
    j = resolvePlanAlignedThinkStepIndex(steps, j)
    return { j, st: steps[j] }
  }
  if (
    Array.isArray(steps) &&
    steps.length === 1 &&
    (ev.index === 0 || ev.index === '0')
  ) {
    return { j: 0, st: steps[0] }
  }
  const running = steps.find((s) => s.status === 'running')
  if (running) {
    j = steps.indexOf(running)
    return { j, st: running }
  }
  j = steps.length - 1
  return { j, st: steps[j] }
}

/** 进入决策块时冻结「思考」墙钟 */
function freezeThoughtPhaseEndForActionXmlWait(st, aiMessage) {
  if (!st || st.thoughtPhaseEndAtMs != null || st.stepStartedAt == null) return
  if (!thoughtStepHasSubstantiveProse(st, aiMessage)) return
  st.thoughtPhaseEndAtMs = Date.now()
}

/**
 * THINK 轨增量：后端已吞主协议 XML；部分模型仍会在 reasoning 里输出 `<reason>` 等泄漏标签，在此剔除。
 */
function appendUnifiedFilteredThinkPiece(aiMessage, j, piece) {
  if (typeof piece !== 'string' || !piece) return ''
  return stripReasoningChannelArtifacts(piece)
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

/** 当前应接收 THINK 草稿的 step 下标：占位阶段固定 0；多步时跟 running 步，避免第二轮仍写 step0 */
function resolveActiveThinkStepIndex(aiMessage) {
  const steps = aiMessage?.steps
  if (!Array.isArray(steps) || !steps.length) return 0
  if (aiMessage._placeholderSteps) return 0
  let j = steps.findIndex((s) => s && s.status === 'running')
  if (j < 0) j = steps.length - 1
  return j
}

/**
 * 计划到达 / 进入工具执行后：收起顶部首轮思考区，冻结 step0，避免与 AgentTaskRun 内第二步「思考中」叠两层。
 */
export function finalizeMessageFirstThinkStream(aiMessage) {
  if (!aiMessage || aiMessage._firstThinkUiSealed) return
  aiMessage._firstThinkUiSealed = true
  aiMessage._reasoningPhaseLive = false
  const vis =
    aiMessage.reasoningDisplayContent ||
    aiMessage.reasoningContent ||
    aiMessage.thinkReasoningDraft ||
    ''
  if (vis) aiMessage.reasoningDisplayContent = vis
  const steps = aiMessage.steps
  if (!Array.isArray(steps)) return
  for (const st of steps) {
    if (!st) continue
    const pk = String(st.phaseWait?.kind || '')
    if (st.phaseWait?.active && (pk === 'think' || pk === 'extended_thinking')) {
      st.phaseWait = null
    }
  }
  if (steps[0]) freezeThoughtSnapshotForStep(steps[0])
}

/** 新一步开始思考前：冻结更早步骤的思考草稿；勿提前 completed（grep 步可能尚未 executing） */
export function sealPriorStepsBeforeThinkRound(aiMessage, stepIndex) {
  if (!aiMessage || stepIndex == null || stepIndex <= 0) return
  const steps = aiMessage.steps
  if (!Array.isArray(steps)) return
  for (let k = 0; k < stepIndex; k++) {
    const st = steps[k]
    if (!st) continue
    freezeThoughtSnapshotForStep(st)
    st.phaseWait = null
    if (st.thoughtPhaseEndAtMs == null && st.thoughtReasoningSnapshot) {
      st.thoughtPhaseEndAtMs = Date.now()
    }
  }
  aiMessage.thinkReasoningDraft = ''
  aiMessage.thinkContentDraft = ''
  aiMessage._reasoningPhaseLive = true
}

/**
 * hello/phase 挂的占位 step：THINK 流只写在 aiMessage，AgentTaskRun 读的是 step.thought*，不同步则长时间只有「...」。
 * 将思考镜像到当前 active step，并清 phaseWait，避免与顶部 loading 重复多段等待动画。
 */
function syncPlaceholderStepThought(aiMessage) {
  const steps = aiMessage?.steps
  if (!Array.isArray(steps) || !steps.length) return
  const j = resolveActiveThinkStepIndex(aiMessage)
  const st = steps[j]
  if (!st) return
  const tr = aiMessage.thinkReasoningDraft || ''
  const tc = aiMessage.thinkContentDraft || ''
  const rc = (aiMessage.reasoningContent || '').replace(/\u200b/g, '')
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
      const durationMs =
        stepEvent.duration_ms != null ? Number(stepEvent.duration_ms) : null
      const briefThr =
        stepEvent.brief_threshold_ms != null ? Number(stepEvent.brief_threshold_ms) : 800

      const applyThoughtTimingToStep = (st, segment) => {
        if (!st || durationMs == null || !Number.isFinite(durationMs)) return
        st.thoughtTiming = {
          durationMs,
          kind: stepEvent.kind || null,
          segment: segment || 'think',
          briefThresholdMs: briefThr
        }
        if (st.thoughtPhaseEndAtMs == null) {
          if (st.stepStartedAt != null) {
            st.thoughtPhaseEndAtMs = st.stepStartedAt + durationMs
          } else {
            st.thoughtPhaseEndAtMs = Date.now()
          }
        }
      }

      if (seg === 'think') {
        if (durationMs != null) aiMessage.reasoningUiDurationMs = durationMs
        if (stepEvent.kind) aiMessage.reasoningUiKind = stepEvent.kind
        if (stepEvent.brief_threshold_ms != null) {
          aiMessage.reasoningBriefThresholdMs = briefThr
        }
        let j =
          stepEvent.index != null ? resolveStreamStepIndex(stepEvent.index, aiMessage.steps) : null
        if (j == null && Array.isArray(aiMessage.steps) && aiMessage.steps.length) j = 0
        if (j != null && aiMessage.steps[j]) applyThoughtTimingToStep(aiMessage.steps[j], 'think')
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
      const thinkTarget = resolveThinkTargetStep(
        aiMessage,
        stepEvent,
        resolveStreamStepIndex
      )
      let j = thinkTarget.j
      const piece = stepEvent.delta
      const rp = stepEvent.react_phase
      /** 仅 react_phase=think（或缺省）写入「行动前 Thought」；observe/decide 走各自字段，避免与 grep 后观察混成第二个「思考」 */
      const isPreActionThink = !rp || rp === 'think'
      const isObserve = rp === 'observe'
      const isDecide = rp === 'decide'

      let pieceVisible = typeof piece === 'string' ? piece : ''
      if (typeof piece === 'string' && piece && (isPreActionThink || isDecide)) {
        pieceVisible = appendUnifiedFilteredThinkPiece(aiMessage, j, piece)
      }
      pieceVisible = stripReasoningChannelArtifacts(pieceVisible)

      const summaryPiece =
        stepEvent.think_summary_delta != null ? String(stepEvent.think_summary_delta) : ''
      if (summaryPiece && !/^frozen_macro_step_\d+$/i.test(summaryPiece.trim())) {
        let sumTarget = resolveThinkTargetStep(
          aiMessage,
          stepEvent,
          resolveStreamStepIndex
        )
        if (!sumTarget.st && ctx.ensureThinkPlaceholder) {
          ctx.ensureThinkPlaceholder(aiMessage)
          sumTarget = resolveThinkTargetStep(
            aiMessage,
            stepEvent,
            resolveStreamStepIndex
          )
        }
        if (sumTarget.st) {
          sumTarget.st.thoughtSummaryDraft =
            (sumTarget.st.thoughtSummaryDraft || '') + summaryPiece
        }
        scheduleReasoningTypewriter(aiMessage)
      }

      const idx = j != null ? j : resolveActiveThinkStepIndex(aiMessage)

      if (typeof piece === 'string' && piece && isObserve) {
        aiMessage.hadAgentThinkPhase = true
        aiMessage.lastReactPhase = 'observe'
        const st = idx != null ? aiMessage.steps[idx] : null
        if (st) {
          st.llmDraft = (st.llmDraft || '') + pieceVisible
          if (st.thoughtPhaseEndAtMs == null) {
            freezeThoughtSnapshotForStep(st)
            st.thoughtPhaseEndAtMs = Date.now()
          }
          if (st.phaseWait?.active) st.phaseWait = null
        }
        scheduleReasoningTypewriter(aiMessage)
        return true
      }

      if (typeof piece === 'string' && piece && isDecide) {
        aiMessage.hadAgentThinkPhase = true
        aiMessage.lastReactPhase = 'decide'
        const st = idx != null ? aiMessage.steps[idx] : null
        if (st) {
          st.reasoningDecideDraft = (st.reasoningDecideDraft || '') + pieceVisible
          if (st.thoughtPhaseEndAtMs == null) {
            freezeThoughtSnapshotForStep(st)
            st.thoughtPhaseEndAtMs = Date.now()
          }
        }
        scheduleReasoningTypewriter(aiMessage)
        return true
      }

      if (typeof piece === 'string' && piece && isPreActionThink) {
        aiMessage.hadAgentThinkPhase = true
        aiMessage._reasoningPhaseLive = true
        if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
        const multi =
          !aiMessage._placeholderSteps &&
          Array.isArray(aiMessage.steps) &&
          aiMessage.steps.length > 1
        if (multi && idx > 0) {
          if (aiMessage.steps[idx]) {
            aiMessage.steps[idx].thoughtReasoningDraft =
              (aiMessage.steps[idx].thoughtReasoningDraft || '') + pieceVisible
          }
        } else {
          aiMessage.thinkReasoningDraft = (aiMessage.thinkReasoningDraft || '') + pieceVisible
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
        }

        if ((!aiMessage.steps || aiMessage.steps.length === 0) && ctx.ensureThinkPlaceholder) {
          ctx.ensureThinkPlaceholder(aiMessage)
        }

        syncPlaceholderStepThought(aiMessage)

        scheduleReasoningTypewriter(aiMessage)
      }
      if (stepEvent.react_phase) {
        aiMessage.lastReactPhase = stepEvent.react_phase
      } else if (isPreActionThink) {
        aiMessage.lastReactPhase = 'think'
      }
      if (j != null && aiMessage.steps[j] && typeof piece === 'string' && piece && isPreActionThink) {
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
        const p = stripReasoningChannelArtifacts(piece)
        if (seg === 'decide') {
          st.reasoningDecideDraft = (st.reasoningDecideDraft || '') + p
        } else if (seg !== 'observe') {
          st.reasoningStepDraft = (st.reasoningStepDraft || '') + p
        }
        if (seg !== 'observe') {
          st.thoughtReasoningDraft = (st.thoughtReasoningDraft || '') + p
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
          // 仅首轮 unified think 保持思考计时；宏路径「准备下一步」属执行衔接，勿当作思考中
          const phaseWaitKeepsThoughtOpen = kind === 'unified_round_think'
          if (
            !phaseWaitKeepsThoughtOpen &&
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
          if (
            (kind === 'preparing_next_step' || kind === 'macro_params_llm') &&
            st.thoughtPhaseEndAtMs == null &&
            st.stepStartedAt != null
          ) {
            st.thoughtPhaseEndAtMs = Date.now()
          }
        } else {
          st.phaseWait = null
          if (kind === 'unified_round_think') {
            const endMs = Date.now()
            const briefThr = 800
            st.thoughtPhaseEndAtMs = endMs
            if (st.stepStartedAt != null && !st.thoughtTiming) {
              const durationMs = Math.max(0, endMs - st.stepStartedAt)
              st.thoughtTiming = {
                durationMs,
                kind: durationMs < briefThr ? 'brief' : 'normal',
                segment: 'think',
                briefThresholdMs: briefThr
              }
            }
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
        st.thoughtContentDraft = (st.thoughtContentDraft || '') + stripReasoningChannelArtifacts(piece)
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
        const isPreActionThink = !rp || rp === 'think'
        const isObserve = rp === 'observe'
        const isDecide = rp === 'decide'
        const rawPiece = isPreActionThink ? appendUnifiedFilteredThinkPiece(aiMessage, j, piece) : piece
        const pieceVisible =
          typeof rawPiece === 'string' ? stripReasoningChannelArtifacts(rawPiece) : ''

        if (isPreActionThink) aiMessage.hadAgentThinkPhase = true
        if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
        aiMessage._reasoningPhaseLive = true
        const multi =
          !aiMessage._placeholderSteps &&
          Array.isArray(aiMessage.steps) &&
          aiMessage.steps.length > 1
        const activeIdx = j != null ? j : resolveActiveThinkStepIndex(aiMessage)

        if (isObserve && activeIdx != null && aiMessage.steps[activeIdx]) {
          const st = aiMessage.steps[activeIdx]
          st.llmDraft = (st.llmDraft || '') + pieceVisible
          if (st.thoughtPhaseEndAtMs == null) {
            freezeThoughtSnapshotForStep(st)
            st.thoughtPhaseEndAtMs = Date.now()
          }
          aiMessage.lastReactPhase = 'observe'
          scheduleReasoningTypewriter(aiMessage)
        } else if (isDecide && activeIdx != null && aiMessage.steps[activeIdx]) {
          aiMessage.steps[activeIdx].reasoningDecideDraft =
            (aiMessage.steps[activeIdx].reasoningDecideDraft || '') + pieceVisible
          aiMessage.lastReactPhase = 'decide'
          scheduleReasoningTypewriter(aiMessage)
        } else if (isPreActionThink && multi && activeIdx > 0 && sc === 'reasoning') {
          if (aiMessage.steps[activeIdx]) {
            aiMessage.steps[activeIdx].thoughtReasoningDraft =
              (aiMessage.steps[activeIdx].thoughtReasoningDraft || '') + pieceVisible
          }
          scheduleReasoningTypewriter(aiMessage)
        } else if (isPreActionThink && multi && activeIdx > 0 && sc === 'content') {
          if (aiMessage.steps[activeIdx]) {
            aiMessage.steps[activeIdx].thoughtContentDraft =
              (aiMessage.steps[activeIdx].thoughtContentDraft || '') + pieceVisible
          }
          scheduleReasoningTypewriter(aiMessage)
        } else if (isPreActionThink && sc === 'reasoning') {
          aiMessage.thinkReasoningDraft = (aiMessage.thinkReasoningDraft || '') + pieceVisible
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
          scheduleReasoningTypewriter(aiMessage)
        } else if (isPreActionThink && sc === 'content') {
          aiMessage.thinkContentDraft = (aiMessage.thinkContentDraft || '') + pieceVisible
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
          scheduleReasoningTypewriter(aiMessage)
        } else {
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
          scheduleReasoningTypewriter(aiMessage)
        }
        if (stepEvent.react_phase) aiMessage.lastReactPhase = stepEvent.react_phase
        else if (isPreActionThink) aiMessage.lastReactPhase = 'think'
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
          const pieceClean = stripReasoningChannelArtifacts(piece)
          aiMessage._thinkTodoMergedIntoReasoning = true
          if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
          aiMessage._reasoningPhaseLive = true
          if (rp === 'think' && sc === 'content') {
            aiMessage.thinkContentDraft = (aiMessage.thinkContentDraft || '') + pieceClean
            aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceClean
            scheduleReasoningTypewriter(aiMessage)
          } else {
            aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceClean
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
  if (aiMessage.reasoningUiDurationMs != null && !s0.thoughtTiming) {
    s0.thoughtTiming = {
      durationMs: Number(aiMessage.reasoningUiDurationMs),
      kind: aiMessage.reasoningUiKind || null,
      segment: 'think',
      briefThresholdMs: aiMessage.reasoningBriefThresholdMs ?? 800
    }
    if (s0.thoughtPhaseEndAtMs == null && s0.stepStartedAt != null) {
      s0.thoughtPhaseEndAtMs = s0.stepStartedAt + Number(aiMessage.reasoningUiDurationMs)
    }
  }
}
