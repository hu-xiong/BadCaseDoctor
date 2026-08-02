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
 * THINK / think_summary 绑定步骤：index 对应 steps[n] 未就绪时回落到 running 或最后一行（对齐 step_log）。
 */
function resolveThinkTargetStep(aiMessage, rawIndex, resolveStreamStepIndex) {
  const steps = aiMessage?.steps
  if (!Array.isArray(steps) || !steps.length) return { j: null, st: null }
  let j = resolveStreamStepIndex(rawIndex, steps)
  if (j != null && steps[j]) return { j, st: steps[j] }
  if (
    Array.isArray(steps) &&
    steps.length === 1 &&
    (rawIndex === 0 || rawIndex === '0')
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

/** LangGraph 多轮：agent_thought / reasoning_timing 的 index 到达时补齐 steps[n]，避免耗时落到 step0 或丢失 */
function ensureThinkStepRow(aiMessage, rawIndex, ctx) {
  if (!aiMessage || rawIndex == null || rawIndex === '') return
  if (typeof ctx?.ensureReactStepsForStreamIndex !== 'function') return
  ctx.ensureReactStepsForStreamIndex(aiMessage, rawIndex)
}

/** 思考结束但未收到 reasoning_timing 时，用墙钟补 thoughtTiming（供眉标 Xs） */
export function synthesizeThoughtTimingIfMissing(st, endMs = Date.now()) {
  if (!st || typeof st !== 'object') return
  if (st.thoughtPhaseEndAtMs == null) st.thoughtPhaseEndAtMs = endMs
  if (st.thoughtTiming?.durationMs != null && Number.isFinite(Number(st.thoughtTiming.durationMs))) {
    return
  }
  const start = st.stepStartedAt
  if (start == null || !Number.isFinite(Number(start))) return
  const durationMs = Math.max(0, Number(st.thoughtPhaseEndAtMs) - Number(start))
  const briefThr = 800
  st.thoughtTiming = {
    durationMs,
    kind: durationMs < briefThr ? 'brief' : 'normal',
    segment: 'think',
    briefThresholdMs: briefThr
  }
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
  } else if (
    aiMessage.lastReactPhase === 'think' ||
    aiMessage.lastReactPhase === 'observe' ||
    aiMessage.lastReactPhase === 'decide'
  ) {
    // 统一流：计划到达后 multiStep 为 true，仍须把 message 级 THINK 草稿同步到 steps[0]（首轮 grep 绑 step0）
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
        if (st.stepStartedAt == null && durationMs > 0) {
          st.stepStartedAt = Date.now() - durationMs
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
        if (stepEvent.index != null) ensureThinkStepRow(aiMessage, stepEvent.index, ctx)
        let j =
          stepEvent.index != null ? resolveStreamStepIndex(stepEvent.index, aiMessage.steps) : null
        if (j == null && Array.isArray(aiMessage.steps) && aiMessage.steps.length) j = 0
        if (j != null && aiMessage.steps[j]) applyThoughtTimingToStep(aiMessage.steps[j], 'think')
      } else if ((seg === 'decide' || seg === 'observe') && stepEvent.index != null) {
        ensureThinkStepRow(aiMessage, stepEvent.index, ctx)
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
      if (stepEvent.index != null) ensureThinkStepRow(aiMessage, stepEvent.index, ctx)
      const thinkTarget = resolveThinkTargetStep(
        aiMessage,
        stepEvent.index,
        resolveStreamStepIndex
      )
      let j = thinkTarget.j
      const piece = stepEvent.delta
      const rp = stepEvent.react_phase
      const isThink =
        !rp || rp === 'think' || (typeof sseIsReactThinkPhase === 'function' && sseIsReactThinkPhase(rp))
      const thinkEnded =
        Number(stepEvent.think_status) === 1 || Number(stepEvent.processType) === 1

      let pieceVisible = typeof piece === 'string' ? piece : ''
      if (typeof piece === 'string' && piece && isThink) {
        pieceVisible = appendUnifiedFilteredThinkPiece(aiMessage, j, piece)
      }
      pieceVisible = stripReasoningChannelArtifacts(pieceVisible)

      const summaryPiece =
        stepEvent.think_summary_delta != null ? String(stepEvent.think_summary_delta) : ''
      if (summaryPiece && !/^frozen_macro_step_\d+$/i.test(summaryPiece.trim())) {
        let sumTarget = resolveThinkTargetStep(
          aiMessage,
          stepEvent.index,
          resolveStreamStepIndex
        )
        if (!sumTarget.st && ctx.ensureThinkPlaceholder) {
          ctx.ensureThinkPlaceholder(aiMessage)
          sumTarget = resolveThinkTargetStep(
            aiMessage,
            stepEvent.index,
            resolveStreamStepIndex
          )
        }
        if (sumTarget.st) {
          sumTarget.st.thoughtSummaryDraft =
            (sumTarget.st.thoughtSummaryDraft || '') + summaryPiece
        }
        scheduleReasoningTypewriter(aiMessage)
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
        if (st.stepStartedAt == null) st.stepStartedAt = Date.now()
        st.status = st.status === 'pending' ? 'running' : st.status
        st.agentThoughtDraft = (st.agentThoughtDraft || '') + pieceVisible
        const vis = pieceVisible.replace(/[\u200B-\u200D\uFEFF\u2060]/g, '').trim()
        if (vis.length > 0 && st.phaseWait?.active) {
          const pk = String(st.phaseWait.kind || '')
          if (pk !== 'unified_action_xml') {
            st.phaseWait = null
          }
        }
      }
      // agent_thought_done：未带 reasoning_timing 时用墙钟补眉标耗时
      if (thinkEnded) {
        aiMessage._reasoningPhaseLive = false
        const endTarget = resolveThinkTargetStep(
          aiMessage,
          stepEvent.index,
          resolveStreamStepIndex
        )
        if (endTarget.st) synthesizeThoughtTimingIfMissing(endTarget.st)
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
        const isThink =
          !rp || rp === 'think' || (typeof sseIsReactThinkPhase === 'function' && sseIsReactThinkPhase(rp))
        /** 与 isThink 对齐：缺省 react_phase 时也应写入 thinkReasoningDraft，勿只写 reasoningContent（否则 plan 到达后不同步到 steps[0]，Thought 空白） */
        const inThinkDraftPhase =
          typeof sseIsReactThinkPhase === 'function' ? sseIsReactThinkPhase(rp) : !rp || rp === 'think'
        const rawPiece = isThink ? appendUnifiedFilteredThinkPiece(aiMessage, j, piece) : piece
        const pieceVisible =
          typeof rawPiece === 'string' ? stripReasoningChannelArtifacts(rawPiece) : ''

        if (sseIsReactThinkPhase(stepEvent.react_phase)) aiMessage.hadAgentThinkPhase = true
        if (aiMessage.reasoningPhaseStartTs == null) aiMessage.reasoningPhaseStartTs = Date.now()
        aiMessage._reasoningPhaseLive = true
        if (inThinkDraftPhase && sc === 'reasoning') {
          aiMessage.thinkReasoningDraft = (aiMessage.thinkReasoningDraft || '') + pieceVisible
          aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + pieceVisible
          scheduleReasoningTypewriter(aiMessage)
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
/** 停止/中断/进入下一轮 THINK 时收尾首轮 THINK 流：同步草稿到 step0、冻结墙钟、清 phaseWait */
export function finalizeMessageFirstThinkStream(aiMessage) {
  if (!aiMessage) return
  syncPlaceholderStepThought(aiMessage)
  if (Array.isArray(aiMessage.steps)) {
    const now = Date.now()
    for (const st of aiMessage.steps) {
      if (!st) continue
      if (st.thoughtPhaseEndAtMs == null && st.stepStartedAt != null) {
        st.thoughtPhaseEndAtMs = now
      }
      if (thoughtStepHasSubstantiveProse(st, aiMessage)) {
        synthesizeThoughtTimingIfMissing(st, st.thoughtPhaseEndAtMs ?? now)
      }
      if (st.phaseWait?.active) {
        st.phaseWait = null
      }
    }
  }
  aiMessage._reasoningPhaseLive = false
}

/** 新一轮 THINK 开始前：将 tsi 之前的 step 标记为已完成（不再 running），避免旧步骤残留运行态 */
export function sealPriorStepsBeforeThinkRound(aiMessage, tsi) {
  if (!aiMessage?.steps || tsi == null || tsi <= 0) return
  for (let i = 0; i < tsi && i < aiMessage.steps.length; i++) {
    const st = aiMessage.steps[i]
    if (!st) continue
    if (st.status === 'running') st.status = 'done'
    if (st.thoughtPhaseEndAtMs == null && st.stepStartedAt != null) {
      st.thoughtPhaseEndAtMs = Date.now()
    }
    if (st.phaseWait?.active) st.phaseWait = null
  }
}

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
