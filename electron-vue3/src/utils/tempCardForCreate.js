/** 新建预览未指定卡片时：内存虚拟卡片 id，用户确认后再 POST /api/cards 落库 */

export const TEMP_CARD_ID_PREFIX = 'vtc:'

export function tempCardScopeKey(projectId, planId, entityType) {
  const pid = planId != null && String(planId).trim() !== '' ? String(planId).trim() : '0'
  const et = normalizeEntityTypeForTempCard(entityType)
  return `${String(projectId)}|${pid}|${et}`
}

export function isVirtualTempCardId(cardId) {
  const s = String(cardId ?? '').trim()
  return s.startsWith(TEMP_CARD_ID_PREFIX)
}

export function buildVirtualTempCardId(scopeKey) {
  return `${TEMP_CARD_ID_PREFIX}${scopeKey}`
}

export function normalizeEntityTypeForTempCard(entityType) {
  const s = String(entityType || 'bug').toLowerCase()
  if (s === 'test_case' || s === 'testcase') return 'testcase'
  if (s === 'badcase') return 'badcase'
  if (s === 'card') return 'card'
  return 'bug'
}

/** 卡片 type 字段（与 CardPanel / createCard API 一致） */
export function entityTypeToCardPanelType(entityType) {
  return normalizeEntityTypeForTempCard(entityType)
}

export function typeListFilterFromEntity(entityType) {
  const et = normalizeEntityTypeForTempCard(entityType)
  if (et === 'badcase') return 'badcase'
  if (et === 'testcase') return 'testcase'
  return 'bug'
}
