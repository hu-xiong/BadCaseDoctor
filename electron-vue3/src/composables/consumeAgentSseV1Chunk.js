/**
 * 消费一条已解析的 Agent SSE v1 JSON（面板流循环内用）。
 * @returns {{ breakChunkLoop?: boolean }}
 */
import {
  applyAgentSseV1HelloChunk,
  applyAgentSseV1PhaseChunk,
  applyAgentSseV1ErrChunk
} from './agentReactStreamReducer.js'
import { applyPlanPayloadV1, applyStepPayloadV1, applyTailPayloadV1 } from './agentReactV1Ui.js'
import { reactSseV1ChunkToLegacyStepEvent } from './reactSseV1ToStepEvent.js'
import { applyReactThinkSSEStepEvent } from './applyReactThinkSSEStepEvent.js'
import { applyReactEngineLaneLegacyStepEvent } from './reactEngineLegacyStream.js'
import { i18n } from '../i18n/index.js'

function logProtocolVersionOnce(aiMessage, chunk, logFn) {
  if (chunk.protocol_version != null && !aiMessage._agentProtocolLogged) {
    aiMessage._agentProtocolLogged = true
    logFn('[CHAT-STREAM] SSE protocol_version:', chunk.protocol_version)
  }
}

function ensureFirstStepPlaceholder(aiMessage, buildReactStepsFromTodoStrings) {
  if (!aiMessage) return
  // 纯对话短路已清空 steps；后续 summary_stream 仍会夹带 phase 边沿，勿再挂占位 step（否则 Thought 空壳 +「未收到行动说明」）
  if (aiMessage.reactDirectChatReply) return
  if (Array.isArray(aiMessage.steps) && aiMessage.steps.length) return
  if (typeof buildReactStepsFromTodoStrings !== 'function') return
  // 仅为挂载 Thought 等待态：隐藏顶部「规划备忘」，避免出现丑的占位计划行
  aiMessage.reactPlanPanelSuppressed = true
  const steps = buildReactStepsFromTodoStrings([''])
  if (!Array.isArray(steps) || !steps.length) return
  const st = steps[0]
  st.status = 'running'
  st.stepStartedAt = Date.now()
  st.phaseWait = { active: true, kind: 'think', message: i18n.global.t('chat.phaseWaitModel') }
  aiMessage.steps = steps
  aiMessage._placeholderSteps = true
}

/**
 * @param {object} chunk
 * @param {object} aiMessage
 * @param {object} ctx
 * @param {function} ctx.scrollToBottom
 * @param {function} ctx.consoleLog 默认 console.log
 * @param {function} ctx.consoleWarn 默认 console.warn
 * @param {boolean} ctx.isDebugReactThinkSSE
 * @param {object} ctx.buildReactStepsFromTodoStrings
 * @param {object} ctx.thinkCtx — 传入 `applyReactThinkSSEStepEvent` 的第三参
 * @param {object} ctx.engineCtx — 传入 `applyReactEngineLaneLegacyStepEvent` 的第三参
 */
export function consumeAgentSseV1Chunk(chunk, aiMessage, ctx) {
  const log = ctx.consoleLog || console.log.bind(console)
  const warn = ctx.consoleWarn || console.warn.bind(console)
  const scrollToBottom = ctx.scrollToBottom
  const isDebugReactThinkSSE = ctx.isDebugReactThinkSSE
  const buildReactStepsFromTodoStrings = ctx.buildReactStepsFromTodoStrings
  const thinkCtx = {
    ...(ctx.thinkCtx || {}),
    ensureThinkPlaceholder:
      (ctx.thinkCtx && ctx.thinkCtx.ensureThinkPlaceholder) ||
      ((msg) => {
        if (!msg || msg.reactDirectChatReply) return
        if (msg.steps && msg.steps.length) return
        ensureFirstStepPlaceholder(msg, buildReactStepsFromTodoStrings)
      })
  }
  const engineCtx = ctx.engineCtx

  if (isDebugReactThinkSSE && aiMessage) {
    if (aiMessage._sseTimingT0 == null) aiMessage._sseTimingT0 = Date.now()
    const dt = Date.now() - aiMessage._sseTimingT0
    try {
      log(`[SSE-TIMING] +${dt}ms type=${chunk?.type || 'unknown'}`)
    } catch {
      // ignore
    }
  }

  if (ctx.verboseChunkLog) {
    log('[CHAT-STREAM] 收到 Chunk:', chunk.type, chunk)
  } else {
    log('[CHAT-STREAM] 收到 Chunk:', chunk.type)
  }
  logProtocolVersionOnce(aiMessage, chunk, log)

  // 用户已点「停止生成」后 UI 已收敛；缓冲区里剩余的 SSE 勿再改 Thought/phaseWait/流式态
  if (aiMessage?.agentResult?.status === 'cancelled') {
    return {}
  }

  if (chunk.type === 'client_action') {
    const p = chunk.payload || {}
    if (p.kind === 'local_run_script') {
      if (!Array.isArray(aiMessage.clientLocalRunCards)) aiMessage.clientLocalRunCards = []
      aiMessage.clientLocalRunCards.push({ ...p })
    }
    if (p.kind === 'terminal_exec' && String(p.command || '').trim()) {
      if (!Array.isArray(aiMessage.pendingTerminalExecQueue)) aiMessage.pendingTerminalExecQueue = []
      const row = {
        command: String(p.command || '').trim(),
        cwd: String(p.cwd || '').trim(),
        timeout: Math.min(86400, Math.max(1, Number(p.timeout) || 60)),
        stop_on_error: p.stop_on_error === true
      }
      aiMessage.pendingTerminalExecQueue.push(row)
      if (!Array.isArray(aiMessage.clientTerminalExecCards)) aiMessage.clientTerminalExecCards = []
      aiMessage.clientTerminalExecCards.push({ ...row, status: 'queued' })
    }
    scrollToBottom()
    return {}
  }

  if (chunk.type === 'heartbeat') {
    // 扩展思维等待期：收到首个 think 状态但尚无可见内容时，显示明确的等待提示
    if (aiMessage && aiMessage._reasoningPhaseLive && !aiMessage._extendedThinkingHintShown) {
      const hasVisibleContent = String(aiMessage.thinkReasoningDraft || '').trim().length >= 2
        || String(aiMessage.reasoningContent || '').trim().length >= 2
      if (!hasVisibleContent) {
        aiMessage._extendedThinkingHintShown = true
        // 触发等待提示更新（由前端模板根据此标志显示）
        if (aiMessage.steps?.[0]) {
          const st = aiMessage.steps[0]
          if (!st.phaseWait?.active) {
            st.phaseWait = { active: true, kind: 'extended_thinking', message: i18n.global.t('chat.extendedThinking') }
          }
        }
      }
    }
    return {}
  }

  if (chunk.type === 'hello') {
    applyAgentSseV1HelloChunk(aiMessage)
    // 不在 hello 挂占位 step：纯对话短路不应先「干占位再清空」；占位改到首轮 THINK 可见流之后（见 applyReactThinkSSEStepEvent）
    scrollToBottom()
    return {}
  }
  if (chunk.type === 'phase') {
    applyAgentSseV1PhaseChunk(aiMessage, chunk.payload || {})
    // 进入 think 阶段时，提前创建占位 step 并显示加载动画
    const pl = chunk.payload || {}
    if (pl.name === 'think' && (!aiMessage.steps || aiMessage.steps.length === 0)) {
      ensureFirstStepPlaceholder(aiMessage, buildReactStepsFromTodoStrings)
    }
    scrollToBottom()
    return {}
  }
  if (chunk.type === 'plan') {
    applyPlanPayloadV1(aiMessage, chunk.payload, buildReactStepsFromTodoStrings)
    scrollToBottom()
    return {}
  }
  if (chunk.type === 'step') {
    applyStepPayloadV1(aiMessage, chunk.payload)
    scrollToBottom()
    return {}
  }
  if (chunk.type === 'tail') {
    applyTailPayloadV1(aiMessage, chunk.payload)
    scrollToBottom()
    return {}
  }
  if (chunk.type === 'err') {
    applyAgentSseV1ErrChunk(aiMessage, chunk.payload || {})
    scrollToBottom()
    return {}
  }

  const stepEvent = reactSseV1ChunkToLegacyStepEvent(chunk)

  if (stepEvent && stepEvent.event) {
    if (!aiMessage.understanding && !aiMessage.reactMainLoopFinished) {
      aiMessage.understanding = '...'
    }
    if (isDebugReactThinkSSE) {
      log('[CHAT-STREAM] v1 内层事件:', stepEvent.event, stepEvent)
    }

    const thinkHandled = applyReactThinkSSEStepEvent(aiMessage, stepEvent, thinkCtx)
    if (thinkHandled) {
      scrollToBottom()
      return {}
    }

    const engine = applyReactEngineLaneLegacyStepEvent(aiMessage, stepEvent, engineCtx)
    scrollToBottom()
    return engine && engine.breakChunkLoop ? { breakChunkLoop: true } : {}
  }

  warn('[CHAT-STREAM] 未识别的 SSE 包:', chunk.type, chunk)
  scrollToBottom()
  return {}
}
