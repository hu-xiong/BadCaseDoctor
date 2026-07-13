/**
 * 将协议 v1 顶层 chunk 转为旧版「内层 step 事件」形状，供现有 reducer 分支消费（P0：单一路径入口）。
 * 返回 null 表示本 chunk 应由调用方直接处理（hello/plan/step/tail/err/heartbeat）。
 */
export function reactSseV1ChunkToLegacyStepEvent(chunk) {
  if (!chunk || typeof chunk !== 'object') return null

  if (chunk.type === 'bye') {
    const p = chunk.payload || {}
    return {
      event: 'done',
      findings: p.findings,
      steps_count: p.steps_count,
      duration: p.duration,
      thinking_time: p.thinking_time,
      summary: p.summary,
      status: p.status,
      react_phase: p.react_phase,
      direct_reply: p.direct_reply === true
    }
  }

  if (chunk.type === 'stream' && chunk.payload?.lane === 'think') {
    const pl = chunk.payload || {}
    if (pl.as === 'agent_thought') {
      const ev = {
        event: 'agent_thought',
        delta: pl.delta != null ? String(pl.delta) : '',
        index: pl.index != null ? pl.index : 0,
        react_phase: pl.react_phase,
        stream_channel: pl.stream_channel || 'reasoning'
      }
      if (pl.think_status != null && pl.think_status !== '') {
        const n = Number(pl.think_status)
        if (!Number.isNaN(n)) ev.think_status = n
      }
      if (pl.processType != null && pl.processType !== '') {
        const n = Number(pl.processType)
        if (!Number.isNaN(n)) ev.processType = n
      }
      if (pl.think_summary_delta != null && String(pl.think_summary_delta)) {
        ev.think_summary_delta = String(pl.think_summary_delta)
      }
      return ev
    }
    return {
      event: 'reasoning',
      content: pl.delta != null ? String(pl.delta) : '',
      react_phase: pl.react_phase,
      stream_channel: pl.stream_channel || 'reasoning'
    }
  }

  if (chunk.type === 'stream' && chunk.payload?.lane === 'plan') {
    const pl = chunk.payload || {}
    const ev = {
      event: 'todos_stream',
      delta: pl.delta != null ? String(pl.delta) : ''
    }
    if (pl.react_phase != null) ev.react_phase = pl.react_phase
    return ev
  }

  if (chunk.type === 'stream' && chunk.payload?.lane === 'summary') {
    const pl = chunk.payload || {}
    if (pl.reset) return { event: 'summary_stream_reset' }
    return {
      event: 'summary_stream',
      delta: pl.delta != null ? String(pl.delta) : ''
    }
  }

  if (chunk.type === 'stream' && chunk.payload?.lane === 'batch_preview') {
    const pl = chunk.payload || {}
    return {
      event: 'batch_preview_row',
      row: pl.row,
      index: pl.index,
      tool: pl.tool,
      reason: pl.reason,
      react_phase: pl.react_phase
    }
  }

  if (chunk.type === 'stream' && chunk.payload?.lane === 'tool_error') {
    const pl = chunk.payload || {}
    return {
      event: 'tool_error',
      message: pl.message != null ? String(pl.message) : '',
      tool: pl.tool,
      index: pl.index,
      step_id: pl.step_id,
      code: pl.code,
      details: pl.details,
      react_phase: pl.react_phase
    }
  }

  if (chunk.type === 'stream' && chunk.payload?.lane === 'running_summary') {
    const pl = chunk.payload || {}
    if (pl.reset) {
      const ev = { event: 'running_summary_stream_reset' }
      if (pl.version != null) ev.version = pl.version
      return ev
    }
    if (pl.done === true) {
      return {
        event: 'running_summary_done',
        full_text: pl.full_text != null ? String(pl.full_text) : '',
        version: pl.version,
        index: pl.step_index
      }
    }
    return {
      event: 'running_summary_stream',
      delta: pl.delta != null ? String(pl.delta) : '',
      version: pl.version,
      index: pl.step_index
    }
  }

  if (chunk.type === 'stream' && chunk.payload?.lane === 'engine') {
    return chunk.payload.data
  }

  if (chunk.type === 'tool') {
    const p = chunk.payload || {}
    if (p.op === 'end') {
      const ev = {
        event: 'observation',
        data: p.body,
        tool: p.name,
        index: p.index,
        step_id: p.step_id,
        summary_nl: p.summary_nl,
        react_phase: p.react_phase
      }
      if (p.duration_ms != null && Number.isFinite(Number(p.duration_ms))) {
        ev.tool_duration_ms = Number(p.duration_ms)
      }
      return ev
    }
    if (p.op === 'start') {
      return {
        event: 'executing',
        tool: p.name,
        index: p.index,
        step_id: p.step_id,
        message: p.message,
        params: p.params,
        reason: p.reason,
        react_phase: p.react_phase
      }
    }
    if (p.op === 'error') {
      const det = p.details && typeof p.details === 'object' ? p.details : {}
      const em =
        p.message != null && String(p.message).trim()
          ? String(p.message).trim()
          : (det.error || det.message || '工具执行失败')
      return {
        event: 'observation',
        data: { ...det, success: false, error: em, ...(p.code != null ? { code: p.code } : {}) },
        tool: p.name,
        index: p.index,
        step_id: p.step_id,
        summary_nl: p.summary_nl,
        react_phase: p.react_phase
      }
    }
  }

  return null
}
