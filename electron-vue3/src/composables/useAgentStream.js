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
      chunks.push(JSON.parse(rest))
    } catch {
      /* 半包或异常行，跳过 */
    }
  }
  return { nextBuffer, chunks }
}

/**
 * 每消费一条解析后的 SSE JSON 后调用：先 flush Vue，再等一帧，保证与网卡流式一致的可视更新（避免同 tick 内多包攒批）。
 * @param {typeof import('vue').nextTick} nextTickFn
 */
export async function yieldAgentSseUiFrame(nextTickFn) {
  await nextTickFn()
  await new Promise((resolve) => requestAnimationFrame(resolve))
}
