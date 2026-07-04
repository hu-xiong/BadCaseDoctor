/** 用户可见正文是否仍含统一 ReAct 协议残留 */
export function looksLikeUnifiedProtocolText(t) {
  const s = String(t || '').toLowerCase()
  if (!s.trim()) return false
  return (
    s.includes('<observation') ||
    s.includes('<thinking') ||
    s.includes('<decision') ||
    s.includes('<goal_done>') ||
    s.includes('<execute>') ||
    s.includes('<tool>') ||
    s.includes('<params>')
  )
}

/** 从展示用正文中剥掉统一协议 XML 标签与块 */
export function stripUnifiedProtocolForDisplay(t) {
  let s = String(t || '')
  s = s.replace(/<decision[\s\S]*?<\/decision>/gi, '')
  s = s.replace(/<observation[\s\S]*?<\/observation>/gi, '')
  s = s.replace(/<thinking[\s\S]*?<\/thinking>/gi, '')
  s = s.replace(
    /<\/?(?:observation|thinking|think_summary|decision|decide|task_plan|step|goal_done|execute|tool|params|reason)\b[^>]*>/gi,
    ''
  )
  s = s.replace(/<[^>]+>/g, '')
  return s.replace(/\n{3,}/g, '\n\n').trim()
}
