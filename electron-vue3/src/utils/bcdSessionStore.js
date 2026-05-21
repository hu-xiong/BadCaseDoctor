/**
 * Tab 级 sessionStorage 治理（对齐 docs/需求文档_sessionStorage会话与任务状态管理.md）
 * L2 加速层：真相仍以 API / 消息为准。
 */

const SCHEMA_VERSION = 1

const createHoldKey = (projectId, sessionId) => {
  const pid = projectId != null && projectId !== '' ? String(projectId) : '0'
  const sid =
    sessionId != null && sessionId !== '' && sessionId !== undefined
      ? String(sessionId)
      : '_none_'
  return `bcd:ss:create-hold:${pid}:${sid}`
}

function readEnvelope (storageKey) {
  try {
    const raw = sessionStorage.getItem(storageKey)
    if (!raw) return null
    const o = JSON.parse(raw)
    if (!o || typeof o !== 'object') return null
    if (o.schemaVersion != null && o.schemaVersion !== SCHEMA_VERSION) return null
    return o
  } catch {
    return null
  }
}

function writeEnvelope (storageKey, payload) {
  try {
    sessionStorage.setItem(
      storageKey,
      JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        updatedAt: Date.now(),
        payload
      })
    )
    return true
  } catch (e) {
    console.warn('[bcdSessionStore] write failed:', storageKey, e)
    return false
  }
}

const emptyCreateHoldPayload = () => ({
  heldCreatesAwaitingCard: {},
  tempCardByScope: {},
  awaitingMessageIds: [],
  nameDraftsByScope: {}
})

/**
 * 新建预览「等待澄清卡片」镜像（held + 临时卡片槽 + 对话区 UI 状态）
 * @returns {import('./bcdSessionStore.js').CreateHoldPayload | null}
 */
export function getCreateHoldPayload (projectId, sessionId) {
  const env = readEnvelope(createHoldKey(projectId, sessionId))
  if (!env?.payload || typeof env.payload !== 'object') return null
  const p = env.payload
  return {
    heldCreatesAwaitingCard:
      p.heldCreatesAwaitingCard && typeof p.heldCreatesAwaitingCard === 'object'
        ? p.heldCreatesAwaitingCard
        : {},
    tempCardByScope:
      p.tempCardByScope && typeof p.tempCardByScope === 'object' ? p.tempCardByScope : {},
    awaitingMessageIds: Array.isArray(p.awaitingMessageIds) ? p.awaitingMessageIds : [],
    nameDraftsByScope:
      p.nameDraftsByScope && typeof p.nameDraftsByScope === 'object' ? p.nameDraftsByScope : {}
  }
}

/** @param {import('./bcdSessionStore.js').CreateHoldPayload} payload */
export function setCreateHoldPayload (projectId, sessionId, payload) {
  if (projectId == null || projectId === '') return false
  const base = emptyCreateHoldPayload()
  const next = {
    heldCreatesAwaitingCard: {
      ...base.heldCreatesAwaitingCard,
      ...(payload?.heldCreatesAwaitingCard || {})
    },
    tempCardByScope: { ...base.tempCardByScope, ...(payload?.tempCardByScope || {}) },
    awaitingMessageIds: payload?.awaitingMessageIds ?? base.awaitingMessageIds,
    nameDraftsByScope: { ...base.nameDraftsByScope, ...(payload?.nameDraftsByScope || {}) }
  }
  const hasHeld = Object.keys(next.heldCreatesAwaitingCard).length > 0
  const hasTemp = Object.keys(next.tempCardByScope).length > 0
  const hasAwait = next.awaitingMessageIds.length > 0
  const hasDrafts = Object.keys(next.nameDraftsByScope).length > 0
  if (!hasHeld && !hasTemp && !hasAwait && !hasDrafts) {
    clearCreateHold(projectId, sessionId)
    return true
  }
  return writeEnvelope(createHoldKey(projectId, sessionId), next)
}

export function patchCreateHold (projectId, sessionId, partial) {
  const prev = getCreateHoldPayload(projectId, sessionId) || emptyCreateHoldPayload()
  return setCreateHoldPayload(projectId, sessionId, { ...prev, ...partial })
}

export function clearCreateHold (projectId, sessionId) {
  try {
    sessionStorage.removeItem(createHoldKey(projectId, sessionId))
  } catch (e) {
    console.warn('[bcdSessionStore] clear create-hold failed', e)
  }
}

/** 从 held 映射推导 awaitingMessageIds */
export function awaitingMessageIdsFromHeld (heldMap) {
  const ids = new Set()
  if (!heldMap || typeof heldMap !== 'object') return []
  for (const h of Object.values(heldMap)) {
    if (h?.messageId != null && h.messageId !== '') ids.add(String(h.messageId))
  }
  return [...ids]
}
