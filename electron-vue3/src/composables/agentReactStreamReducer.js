/**
 * Agent SSE v1 薄层 reducer（承接需求 §6.5 / P0P1：从 SimpleChatPanel 逐步迁入）。
 */

/**
 * @param {object} aiMessage
 * @param {object} payload chunk.payload（type=phase）
 */
export function applyAgentSseV1PhaseChunk(aiMessage, payload) {
  if (!aiMessage || !payload) return
  if (payload.name) aiMessage.lastReactPhase = payload.name
  if (payload.n != null && Number.isFinite(Number(payload.n))) {
    aiMessage.reactPhaseNum = Number(payload.n)
  }
}

/** @param {object} aiMessage */
export function applyAgentSseV1HelloChunk(aiMessage) {
  if (!aiMessage) return
  // 收到 hello 即表示 SSE 已连通；勿保持 '...' 三点（用户会误以为卡死）
  if (!aiMessage.understanding || aiMessage.understanding === '...') {
    aiMessage.understanding = ''
  }
}

/**
 * @param {object} j 任意已解析的 SSE JSON（调试用分类）
 * @returns {'heartbeat'|'hello'|'phase'|'plan'|'step'|'tool'|'tail'|'bye'|'err'|'stream'|'unknown'}
 */
export function classifyAgentSseChunk(j) {
  const t = j && typeof j === 'object' ? j.type : ''
  if (t === 'heartbeat') return 'heartbeat'
  if (t === 'hello') return 'hello'
  if (t === 'phase') return 'phase'
  if (t === 'plan') return 'plan'
  if (t === 'step') return 'step'
  if (t === 'tool') return 'tool'
  if (t === 'tail') return 'tail'
  if (t === 'bye') return 'bye'
  if (t === 'err') return 'err'
  if (t === 'stream') return 'stream'
  return 'unknown'
}

/**
 * @param {object} aiMessage
 * @param {object} payload chunk.payload（type=err）
 */
export function applyAgentSseV1ErrChunk(aiMessage, payload) {
  if (!aiMessage) return
  const msg = payload?.message != null ? String(payload.message) : '错误'
  aiMessage.finalResponse = `❌ ${msg}`
}
