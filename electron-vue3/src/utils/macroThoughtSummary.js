/** 宏路径内部 reason / think_summary，不应展示在「思考」折叠头下 */
export function isInternalMacroThoughtSummary (text) {
  const t = String(text || '').trim()
  if (!t) return false
  return /^frozen_macro_step_\d+$/i.test(t)
}

export function sanitizeThoughtSummaryForDisplay (text) {
  const t = String(text || '').trim()
  if (isInternalMacroThoughtSummary(t)) return ''
  return t
}

/** 历史落库 steps 清洗：去掉宏内部摘要，macroExecOnly 且无正文时不保留空思考壳 */
export function sanitizeHistoricalAgentSteps (steps) {
  if (!Array.isArray(steps)) return steps
  return steps.map((s) => {
    if (!s || typeof s !== 'object') return s
    const row = { ...s }
    if (row.thoughtSummarySnapshot != null) {
      row.thoughtSummarySnapshot = sanitizeThoughtSummaryForDisplay(row.thoughtSummarySnapshot)
    }
    if (row.thoughtSummaryDraft != null) {
      row.thoughtSummaryDraft = sanitizeThoughtSummaryForDisplay(row.thoughtSummaryDraft)
    }
    return row
  })
}
