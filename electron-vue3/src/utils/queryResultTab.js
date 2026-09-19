/**
 * 「检索结果」工作台 Tab：查询条件规范化 / 去重签名 / 标题构造。
 * 字段与后端 POST /api/projects/<id>/grep-replay 的 payload 保持一致。
 */

/** 只保留重放相关字段并统一为字符串，用于去重签名与展示 */
export function normalizeQueryPayload (p) {
  const s = (v) => (v == null ? '' : String(v).trim())
  return {
    keywords: s(p?.keywords),
    assignee: s(p?.assignee),
    status: s(p?.status),
    target: s(p?.target) || 'all',
    plan_id: s(p?.plan_id),
    card_id: s(p?.card_id)
  }
}

/** 稳定字符串散列（djb2）→ base36，用作 Tab id 后缀 */
function hashStr (s) {
  let h = 5381
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) >>> 0
  }
  return h.toString(36)
}

/** 稳定字符串哈希（djb2）：同条件复用同一 Tab id，避免开一堆重复结果集 */
export function hashQueryPayload (p) {
  return hashStr(JSON.stringify(normalizeQueryPayload(p)))
}

/** 无查询条件（如历史消息）：用命中集合前几个 id + 条数做签名，同集合复用 Tab、不同集合不互踩 */
export function hashItemsSignature (items) {
  const arr = Array.isArray(items) ? items : []
  const ids = arr
    .slice(0, 3)
    .map((i) => String(i?.record_id ?? i?.bug_id ?? i?.card_id ?? i?.id ?? ''))
    .join('|')
  return hashStr(`${ids}#${arr.length}`)
}

/** 是否存在可用于重放的查询条件（与后端 grep-replay 的兜底校验一致） */
export function hasQueryPayloadCondition (p) {
  const n = normalizeQueryPayload(p)
  return !!(n.keywords || n.assignee || n.status || n.plan_id)
}

const TYPE_LABEL_KEYS = {
  bug: 'chat.navLabelBug',
  badcase: 'chat.navLabelBadcase',
  testcase: 'chat.navLabelTestcase',
  test_case: 'chat.navLabelTestcase',
  card: 'chat.navLabelCard',
  plan: 'chat.navLabelPlan',
  all: 'queryResult.typeAll'
}

/** 标题：`{负责人/关键词} · {类型}`，如「huba · Bug」；无条件时仅类型名 */
export function buildQueryResultTabTitle (payload, t) {
  const p = normalizeQueryPayload(payload)
  const parts = []
  if (p.assignee) parts.push(p.assignee)
  if (p.keywords) parts.push(`「${p.keywords}」`)
  const typeKey = TYPE_LABEL_KEYS[p.target] || TYPE_LABEL_KEYS.all
  const typeLabel = typeof t === 'function' ? t(typeKey) : p.target
  const head = parts.join(' ')
  return head ? `${head} · ${typeLabel}` : typeLabel
}
