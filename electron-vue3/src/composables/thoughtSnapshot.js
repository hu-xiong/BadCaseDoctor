/**
 * 步骤进入 completed 前冻结「行动前思考」正文，避免 Vue 条件渲染在 status 切换后丢失草稿导致 Thought 空白。
 */
export function snapshotThoughtReasoningFromStep(s) {
  if (!s || typeof s !== 'object') return ''
  const chunks = [s.agentThoughtDraft, s.reasoningDecideDraft, s.reasoningStepDraft]
    .map((x) => (x && String(x).trim()) || '')
    .filter(Boolean)
  if (chunks.length) return chunks.join('\n\n')
  const u = (s.thoughtReasoningDraft || '').trim()
  return u ? String(s.thoughtReasoningDraft) : ''
}

export function snapshotThoughtContentFromStep(s) {
  if (!s || typeof s !== 'object') return ''
  const raw = String(s.thoughtContentDraft || '').trim()
  // 过滤掉包含XML标签的内容（与 AgentTaskRun.vue thoughtContentRaw 保持一致）
  if (/<decision|<execute|<tool\b|<params|<reason\b|<result\b/i.test(raw)) {
    return ''
  }
  return raw
}

/** 在置为 completed / 等价终态前调用，写入 thoughtReasoningSnapshot / thoughtContentSnapshot */
export function freezeThoughtSnapshotForStep(s) {
  if (!s || typeof s !== 'object') return
  const r = snapshotThoughtReasoningFromStep(s)
  const c = snapshotThoughtContentFromStep(s)
  if (r) s.thoughtReasoningSnapshot = r
  if (c) s.thoughtContentSnapshot = c
}
