/**
 * Agent `/api/agent/react` SSE：可复用的缓冲区折叠与 JSON 解析（需求 §6.5 / P0P1）。
 * 完整 fetch+auth 仍由 SimpleChatPanel 内联；此处提供纯函数便于单测与逐步迁移。
 */

export { createReactAiMessageState } from './createReactAiMessageState.js'
export { applyPlanPayloadV1, applyStepPayloadV1, applyTailPayloadV1 } from './agentReactV1Ui.js'
export {
  applyAgentSseV1PhaseChunk,
  applyAgentSseV1HelloChunk,
  applyAgentSseV1ErrChunk,
  classifyAgentSseChunk
} from './agentReactStreamReducer.js'
export {
  applyReactObservationLegacyStepEvent,
  shouldMergeModifyPreviewItems,
  DETAIL_FIELDS,
  extractToolName,
  buildStepResultSummary
} from './reactObservationStream.js'
export { applyReactEngineLaneLegacyStepEvent } from './reactEngineLegacyStream.js'
export { consumeAgentSseV1Chunk } from './consumeAgentSseV1Chunk.js'
export { reactSseV1ChunkToLegacyStepEvent } from './reactSseV1ToStepEvent.js'
export { applyReactThinkSSEStepEvent } from './applyReactThinkSSEStepEvent.js'

import JSONBigInt from 'json-bigint'

/** 雪花 ID > Number.MAX_SAFE_INTEGER，SSE 必须用 json-bigint，避免精度丢失 */
const _sseJsonBig = JSONBigInt({ storeAsString: true })

/**
 * 将 UTF-8 增量文本折叠为按行切分，并解析 `data: {json}` 为对象数组。
 * @param {string} buffer 上次未完结的半行
 * @param {string} chunkText decoder.decode 的新增片段
 * @returns {{ nextBuffer: string, chunks: object[] }}
 */
export function foldAgentSseText(buffer, chunkText) {
  const buf = (buffer || '') + (chunkText || '')
  const lines = buf.split('\n')
  const nextBuffer = lines.pop() ?? ''
  const chunks = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith(':') || !trimmed.startsWith('data:')) continue
    const rest = trimmed.slice(5).replace(/^\s*/, '')
    if (!rest || rest === '[DONE]') continue
    try {
      chunks.push(_sseJsonBig.parse(rest))
    } catch {
      try {
        chunks.push(JSON.parse(rest))
      } catch {
        /* 半包或异常行，跳过 */
      }
    }
  }
  return { nextBuffer, chunks }
}

/**
 * 每消费一条解析后的 SSE JSON 后调用：先 flush Vue，再等一帧（续流批量回放等低频场景）。
 * @param {typeof import('vue').nextTick} nextTickFn
 */
export async function yieldAgentSseUiFrame(nextTickFn) {
  await nextTickFn()
  await new Promise((resolve) => requestAnimationFrame(resolve))
}

/**
 * 在线 SSE：think/summary 等 stream 增量只改数据、不每包 paint；工具/阶段/tail 等立即刷。
 * @param {object} chunk 已解析 SSE JSON
 */
export function sseChunkNeedsImmediatePaint(chunk) {
  if (!chunk || typeof chunk !== 'object') return false
  const t = chunk.type
  if (t === 'heartbeat') return false
  if (t === 'stream') {
    const lane = String(chunk.payload?.lane || '')
    return lane === 'batch_preview' || lane === 'tool_error'
  }
  return true
}

/**
 * 在线 SSE UI 合并调度：同一事件循环内 N 个 JSON 只触发一次 nextTick+rAF，且限制最高刷新率。
 * @param {typeof import('vue').nextTick} nextTickFn
 * @param {{ minIntervalMs?: number }} [opts] 默认 ~30fps
 */
export function createSseUiPaintScheduler(nextTickFn, opts = {}) {
  const minIntervalMs = Math.max(16, Number(opts.minIntervalMs) || 32)
  let dirty = false
  let rafId = null
  let timerId = null
  let lastPaintAt = 0
  /** @type {Promise<void>|null} */
  let inflight = null

  const runPaint = async () => {
    rafId = null
    timerId = null
    if (!dirty) return
    dirty = false
    lastPaintAt = performance.now()
    await nextTickFn()
    await new Promise((resolve) => requestAnimationFrame(resolve))
  }

  const schedule = () => {
    dirty = true
    if (rafId != null || timerId != null || inflight) return
    const elapsed = performance.now() - lastPaintAt
    const wait = Math.max(0, minIntervalMs - elapsed)
    const armRaf = () => {
      rafId = requestAnimationFrame(() => {
        rafId = null
        inflight = runPaint().finally(() => {
          inflight = null
        })
      })
    }
    if (wait <= 2) {
      armRaf()
    } else {
      timerId = setTimeout(() => {
        timerId = null
        armRaf()
      }, wait)
    }
  }

  const flushNow = async () => {
    if (timerId != null) {
      clearTimeout(timerId)
      timerId = null
    }
    if (rafId != null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    dirty = true
    if (inflight) {
      await inflight
      if (!dirty) return
    }
    inflight = runPaint().finally(() => {
      inflight = null
    })
    await inflight
  }

  const drain = async () => {
    if (inflight) await inflight
    else if (dirty) await flushNow()
  }

  const dispose = () => {
    if (timerId != null) clearTimeout(timerId)
    if (rafId != null) cancelAnimationFrame(rafId)
    timerId = null
    rafId = null
    dirty = false
    inflight = null
  }

  return { schedule, flushNow, drain, dispose }
}
