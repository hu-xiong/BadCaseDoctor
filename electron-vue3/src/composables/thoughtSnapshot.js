import { stripReasoningChannelArtifacts } from '../utils/stripReasoningChannelArtifacts.js'

function stripUnifiedDecisionBlocks(t) {
  return String(t || '')
    .replace(/<decision[\s\S]*?<\/decision>/gi, '')
    .trim()
}

/**
 * 合并 step 上 mirror 的 thoughtReasoningDraft 与流式 agentThought*。
 * 统一流：计划到达前正文在 thinkReasoningDraft，之后只在 agentThoughtDraft 追加，仅取一侧会丢掉「正在准备上下文」或前半段流式。
 */
export function mergedThoughtReasoningProseFromStep(s) {
  if (!s || typeof s !== 'object') return ''
  const chunks = [s.agentThoughtDraft, s.reasoningDecideDraft, s.reasoningStepDraft]
    .map((x) => (x && String(x).trim()) || '')
    .filter(Boolean)
  const fromChunks = chunks.length ? chunks.join('\n\n') : ''
  const fromDraft = String(s.thoughtReasoningDraft || '').replace(/\u200b/g, '').trim()
  let merged = ''
  if (fromChunks && fromDraft) {
    merged = fromChunks.includes(fromDraft) ? fromChunks : `${fromDraft}\n\n${fromChunks}`
  } else {
    merged = fromChunks || fromDraft
  }
  let out = stripUnifiedDecisionBlocks(merged).trim()
  out = stripReasoningChannelArtifacts(out).trim()
  return out
}

/**
 * 步骤进入 completed 前冻结「行动前思考」正文，避免 Vue 条件渲染在 status 切换后丢失草稿导致 Thought 空白。
 */
export function snapshotThoughtReasoningFromStep(s) {
  return mergedThoughtReasoningProseFromStep(s)
}

export function snapshotThoughtContentFromStep(s) {
  if (!s || typeof s !== 'object') return ''
  const raw = String(s.thoughtContentDraft || '').trim()
  // 过滤掉包含XML标签的内容（与 AgentTaskRun.vue thoughtContentRaw 保持一致）
  if (/<decision|<execute|<tool\b|<params|<reason\b|<result\b/i.test(raw)) {
    return ''
  }
  return stripReasoningChannelArtifacts(raw).trim()
}

/** 在置为 completed / 等价终态前调用，写入 thoughtReasoningSnapshot / thoughtContentSnapshot */
export function freezeThoughtSnapshotForStep(s) {
  if (!s || typeof s !== 'object') return
  const r = snapshotThoughtReasoningFromStep(s)
  const c = snapshotThoughtContentFromStep(s)
  if (r) s.thoughtReasoningSnapshot = r
  if (c) s.thoughtContentSnapshot = c
}
