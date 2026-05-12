/**
 * Qwen / DashScope（含 qwen-3.5-plus）在 reasoning 通道常泄漏 `</reason>`、`<think>` 等；
 * 先 NFKC 规整再剥标签。合并 step 上多段 draft 时也必须调用（见 thoughtSnapshot）。
 */
export function stripReasoningChannelArtifacts(s) {
  if (s == null || typeof s !== 'string') return s
  let t = s
  try {
    t = s.normalize('NFKC')
  } catch {
    t = s
  }
  for (let i = 0; i < 4; i++) {
    const prev = t
    t = t
      .replace(/<\/{0,1}\s*reason(?:ing)?\s*>/gi, '')
      .replace(/<\/{0,1}\s*redacted_reasoning\s*>/gi, '')
      .replace(/<\/{0,1}\s*redacted_thinking\s*>/gi, '')
      .replace(/<\/?reason\b[^>]*>/gi, '')
      .replace(/<\/?reasoning\b[^>]*>/gi, '')
      .replace(/<\/?redacted_reasoning\b[^>]*>/gi, '')
      .replace(/<\/?redacted_thinking\b[^>]*>/gi, '')
      .replace(/<\/{0,1}\s*reason(?:ing)?[^>]*$/gi, '')
    if (t === prev) break
  }
  return t
}
