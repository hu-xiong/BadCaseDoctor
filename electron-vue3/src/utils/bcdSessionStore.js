/**
 * Tab 级 sessionStorage 治理（对齐 docs/需求文档_sessionStorage会话与任务状态管理.md）
 * L2 加速层：真相仍以 API / 消息为准。
 */

import {
  BCD_SS_SCHEMA_VERSION,
  BCD_SS_PREFIX,
  projectSessionKey,
  createHoldKey,
  agentRunKey,
  agentRunSnapshotKey,
  diffBridgeKey,
  tabIndexKey,
  tabDocKey,
  LEGACY_PENDING_MODIFY_DIFF
} from './bcdSessionStore.keys.js'

const SCHEMA_VERSION = BCD_SS_SCHEMA_VERSION
/** 单项目 tabdoc 键数量上限（M2 LRU） */
export const TAB_DOC_MAX_KEYS = 20
/** 单 tabdoc 建议体积（字节），超出时降级 view / listSnapshot */
const TAB_DOC_SOFT_MAX_BYTES = 128 * 1024

const _tabDocTouchOrder = new Map()

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

function writeEnvelope (storageKey, payload, opts = {}) {
  const body = {
    schemaVersion: SCHEMA_VERSION,
    updatedAt: Date.now(),
    payload
  }
  const tryWrite = (pl) => {
    sessionStorage.setItem(storageKey, JSON.stringify({ ...body, payload: pl }))
    return true
  }
  try {
    return tryWrite(payload)
  } catch (e) {
    if (!opts.allowShrink) {
      console.warn('[bcdSessionStore] write failed:', storageKey, e)
      return false
    }
    const shrunk = { ...payload }
    if (shrunk.view) shrunk.view = {}
    if (shrunk.listSnapshot) shrunk.listSnapshot = null
    try {
      return tryWrite(shrunk)
    } catch (e2) {
      console.warn('[bcdSessionStore] write failed after shrink:', storageKey, e2)
      return false
    }
  }
}

function touchTabDocKey (storageKey) {
  _tabDocTouchOrder.set(storageKey, Date.now())
}

function tabDocKeysForProject (userId, projectId) {
  const prefix = `${BCD_SS_PREFIX}tabdoc:${String(userId)}:${String(projectId)}:`
  const rows = []
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i)
      if (k && k.startsWith(prefix)) rows.push(k)
    }
  } catch {
    /* ignore */
  }
  return rows
}

/**
 * LRU：保留 keepTabIds 对应键，删除最久未 touch 的 tabdoc
 */
export function evictTabDocsLRU (userId, projectId, keepTabIds = []) {
  if (userId == null || projectId == null) return
  const keep = new Set(
    (keepTabIds || []).map((id) => tabDocKey(userId, projectId, id))
  )
  const keys = tabDocKeysForProject(userId, projectId)
  if (keys.length <= TAB_DOC_MAX_KEYS) return
  const scored = keys
    .filter((k) => !keep.has(k))
    .map((k) => ({ k, t: _tabDocTouchOrder.get(k) || 0 }))
    .sort((a, b) => a.t - b.t)
  let n = keys.length - TAB_DOC_MAX_KEYS
  for (const { k } of scored) {
    if (n <= 0) break
    try {
      sessionStorage.removeItem(k)
      _tabDocTouchOrder.delete(k)
    } catch {
      /* ignore */
    }
    n -= 1
  }
}

const emptyProjectSessionPayload = () => ({
  activeSessionId: null,
  openSessionIds: [],
  draftBySession: {},
  scrollAnchorBySession: {},
  streamingHint: null
})

// —— 5.1 项目会话上下文 ——

export function getProjectSession (projectId) {
  const env = readEnvelope(projectSessionKey(projectId))
  if (!env?.payload || typeof env.payload !== 'object') return emptyProjectSessionPayload()
  const p = env.payload
  return {
    activeSessionId: p.activeSessionId ?? null,
    openSessionIds: Array.isArray(p.openSessionIds) ? p.openSessionIds : [],
    draftBySession:
      p.draftBySession && typeof p.draftBySession === 'object' ? p.draftBySession : {},
    scrollAnchorBySession:
      p.scrollAnchorBySession && typeof p.scrollAnchorBySession === 'object'
        ? p.scrollAnchorBySession
        : {},
    streamingHint: p.streamingHint ?? null
  }
}

export function patchProjectSession (projectId, partial) {
  if (projectId == null || projectId === '') return false
  const prev = getProjectSession(projectId)
  return writeEnvelope(projectSessionKey(projectId), { ...prev, ...partial })
}

export function setActiveSession (projectId, sessionId) {
  return patchProjectSession(projectId, {
    activeSessionId: sessionId != null && sessionId !== '' ? sessionId : null
  })
}

export function getActiveSessionId (projectId) {
  return getProjectSession(projectId).activeSessionId ?? null
}

/**
 * 若缓存的 sessionId 仍在服务端列表中则返回，否则 null
 * @param {number|string} projectId
 * @param {{ id: number }[]} sessionList
 */
export function resolveActiveSession (projectId, sessionList) {
  const id = getActiveSessionId(projectId)
  if (id == null) return null
  const list = Array.isArray(sessionList) ? sessionList : []
  const exists = list.some((s) => s && s.id === id)
  return exists ? id : null
}

export function saveDraft (projectId, sessionId, text) {
  if (projectId == null || sessionId == null) return false
  const prev = getProjectSession(projectId)
  const drafts = { ...prev.draftBySession, [String(sessionId)]: String(text ?? '') }
  return patchProjectSession(projectId, { draftBySession: drafts })
}

export function getDraft (projectId, sessionId) {
  if (projectId == null || sessionId == null) return ''
  const drafts = getProjectSession(projectId).draftBySession
  const v = drafts[String(sessionId)]
  return v != null ? String(v) : ''
}

export function clearDraft (projectId, sessionId) {
  if (projectId == null || sessionId == null) return false
  const prev = getProjectSession(projectId)
  const drafts = { ...prev.draftBySession }
  delete drafts[String(sessionId)]
  return patchProjectSession(projectId, { draftBySession: drafts })
}

/** 删除会话时从 project 缓存剔除 */
export function removeSessionFromProjectCache (projectId, sessionId) {
  if (projectId == null || sessionId == null) return false
  const sid = String(sessionId)
  const prev = getProjectSession(projectId)
  const openSessionIds = (prev.openSessionIds || []).filter((x) => String(x) !== sid)
  const draftBySession = { ...prev.draftBySession }
  const scrollAnchorBySession = { ...prev.scrollAnchorBySession }
  delete draftBySession[sid]
  delete scrollAnchorBySession[sid]
  let activeSessionId = prev.activeSessionId
  if (activeSessionId != null && String(activeSessionId) === sid) {
    activeSessionId = openSessionIds[0] ?? null
  }
  return patchProjectSession(projectId, {
    activeSessionId,
    openSessionIds,
    draftBySession,
    scrollAnchorBySession
  })
}

// —— 5.3 Diff 详情桥接 ——

export function diffRecordKey (target, targetId) {
  const t = String(target || 'bug').toLowerCase().replace(/-/g, '_')
  const id = targetId != null && targetId !== '' ? String(targetId) : ''
  return `${t}:${id}`
}

const emptyDiffBridge = () => ({
  activeKey: null,
  slots: {}
})

export function getDiffBridge (projectId) {
  const env = readEnvelope(diffBridgeKey(projectId))
  if (!env?.payload || typeof env.payload !== 'object') return emptyDiffBridge()
  const p = env.payload
  return {
    activeKey: p.activeKey ?? null,
    slots: p.slots && typeof p.slots === 'object' ? { ...p.slots } : {}
  }
}

/** M0：旧单键 pendingModifyDiff → bcd:ss:diff 后删除旧键 */
export function migrateLegacyPendingModifyDiff (projectId) {
  if (projectId == null || projectId === '') return false
  try {
    const raw = sessionStorage.getItem(LEGACY_PENDING_MODIFY_DIFF)
    if (!raw) return false
    const data = JSON.parse(raw)
    if (!data || typeof data !== 'object') {
      sessionStorage.removeItem(LEGACY_PENDING_MODIFY_DIFF)
      return false
    }
    const target = data.target || 'bug'
    const targetId = data.targetId ?? data.target_id
    if (targetId == null || targetId === '') return false
    const key = diffRecordKey(target, targetId)
    const prev = getDiffBridge(projectId)
    if (!prev.slots[key]) {
      writeEnvelope(diffBridgeKey(projectId), {
        activeKey: key,
        slots: { ...prev.slots, [key]: { ...data, target, targetId: String(targetId) } }
      })
    }
    sessionStorage.removeItem(LEGACY_PENDING_MODIFY_DIFF)
    return true
  } catch {
    return false
  }
}

/**
 * 写入详情 Diff 槽（最新合并结果整槽替换）；M0 双写 legacy 单键供未迁移读者。
 * @returns {string} slot key
 */
export function setDiffSlot (projectId, diffData, tabSyncOpts = null) {
  if (projectId == null || !diffData || typeof diffData !== 'object') return null
  migrateLegacyPendingModifyDiff(projectId)
  const target = diffData.target || 'bug'
  const targetId = String(diffData.targetId ?? diffData.target_id ?? '')
  if (!targetId) return null
  const key = diffRecordKey(target, targetId)
  const prev = getDiffBridge(projectId)
  const slots = {
    ...prev.slots,
    [key]: { ...diffData, target, targetId }
  }
  writeEnvelope(diffBridgeKey(projectId), { activeKey: key, slots })
  if (tabSyncOpts?.userId != null && tabSyncOpts?.workbenchTabId) {
    patchTabDocWorking(tabSyncOpts.userId, projectId, tabSyncOpts.workbenchTabId, key, {
      target,
      targetId,
      status: 'pending',
      diff: diffData.diff,
      modificationsMirror:
        diffData.modifications && typeof diffData.modifications === 'object'
          ? { ...diffData.modifications }
          : {},
      messageId: diffData.messageId ?? null,
      sessionId: diffData.sessionId ?? null,
      lifecycleId: diffData.lifecycleId ?? diffData.lifecycle_id ?? null,
      diffFingerprint: diffData.diffFingerprint ?? diffData.diff_fingerprint ?? null,
      cachedAt: Date.now()
    })
  }
  try {
    sessionStorage.setItem(
      LEGACY_PENDING_MODIFY_DIFF,
      JSON.stringify(slots[key])
    )
  } catch (e) {
    console.warn('[bcdSessionStore] legacy pendingModifyDiff dual-write failed', e)
  }
  return key
}

export function getDiffSlot (projectId, key) {
  migrateLegacyPendingModifyDiff(projectId)
  const b = getDiffBridge(projectId)
  return key != null ? b.slots[String(key)] ?? null : null
}

/** 详情页读取：等价原 sessionStorage.getItem + JSON.parse */
export function getPendingModifyDiffForDetail (projectId) {
  migrateLegacyPendingModifyDiff(projectId)
  const b = getDiffBridge(projectId)
  if (!b.activeKey) return null
  const slot = b.slots[b.activeKey]
  return slot && typeof slot === 'object' ? { ...slot } : null
}

export function clearDiffSlot (projectId, key) {
  if (projectId == null || key == null) return false
  const b = getDiffBridge(projectId)
  const slots = { ...b.slots }
  delete slots[String(key)]
  let activeKey = b.activeKey
  if (activeKey === String(key)) {
    const rest = Object.keys(slots)
    activeKey = rest.length ? rest[0] : null
  }
  if (Object.keys(slots).length === 0) {
    clearAllDiffBridge(projectId)
    return true
  }
  writeEnvelope(diffBridgeKey(projectId), { activeKey, slots })
  if (activeKey && slots[activeKey]) {
    try {
      sessionStorage.setItem(LEGACY_PENDING_MODIFY_DIFF, JSON.stringify(slots[activeKey]))
    } catch {
      /* ignore */
    }
  } else {
    try {
      sessionStorage.removeItem(LEGACY_PENDING_MODIFY_DIFF)
    } catch {
      /* ignore */
    }
  }
  return true
}

export function clearAllDiffBridge (projectId) {
  try {
    sessionStorage.removeItem(diffBridgeKey(projectId))
    sessionStorage.removeItem(LEGACY_PENDING_MODIFY_DIFF)
  } catch (e) {
    console.warn('[bcdSessionStore] clearAllDiffBridge failed', e)
  }
}

/** 与 GET diff-reviews pending 对齐：删掉服务端已不存在的 slot */
export function reconcileDiffSlots (projectId, pendingKeys) {
  if (projectId == null) return
  migrateLegacyPendingModifyDiff(projectId)
  const allowed = new Set((pendingKeys || []).map((k) => String(k)))
  const b = getDiffBridge(projectId)
  const slots = { ...b.slots }
  let changed = false
  for (const k of Object.keys(slots)) {
    if (!allowed.has(k)) {
      delete slots[k]
      changed = true
    }
  }
  let activeKey = b.activeKey
  if (activeKey && !slots[activeKey]) {
    const keys = Object.keys(slots)
    activeKey = keys.length ? keys[0] : null
    changed = true
  }
  if (!changed) return
  if (Object.keys(slots).length === 0) {
    clearAllDiffBridge(projectId)
    return
  }
  writeEnvelope(diffBridgeKey(projectId), { activeKey, slots })
  if (activeKey && slots[activeKey]) {
    try {
      sessionStorage.setItem(LEGACY_PENDING_MODIFY_DIFF, JSON.stringify(slots[activeKey]))
    } catch {
      /* ignore */
    }
  }
}

export function clearDiffSlotsForSession (projectId, sessionId) {
  if (projectId == null || sessionId == null) return
  const sid = String(sessionId)
  const b = getDiffBridge(projectId)
  const slots = { ...b.slots }
  let changed = false
  for (const [k, slot] of Object.entries(slots)) {
    if (slot && String(slot.sessionId) === sid) {
      delete slots[k]
      changed = true
    }
  }
  if (!changed) return
  if (Object.keys(slots).length === 0) {
    clearAllDiffBridge(projectId)
    return
  }
  let activeKey = b.activeKey
  if (activeKey && !slots[activeKey]) {
    activeKey = Object.keys(slots)[0] ?? null
  }
  writeEnvelope(diffBridgeKey(projectId), { activeKey, slots })
}

export function clearPendingModifyDiffForDetail (projectId) {
  clearAllDiffBridge(projectId)
}

// —— 5.5 新建预览 create-hold（已实现 API，ProjectDetail 接入见文档 §15） ——

const emptyCreateHoldPayload = () => ({
  heldCreatesAwaitingCard: {},
  tempCardByScope: {},
  awaitingMessageIds: [],
  nameDraftsByScope: {}
})

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

// —— 5.2 Agent 运行态镜像（续流） ——

const emptyAgentRunPayload = () => ({
  runId: null,
  messageId: null,
  clientMessageId: null,
  status: 'idle',
  startedAt: null,
  updatedAt: null,
  lastSeq: 0,
  llmModel: null,
  uiSnapshot: null
})

function readAgentRunMetaPayload (projectId, chatSessionId) {
  const env = readEnvelope(agentRunKey(projectId, chatSessionId))
  if (!env?.payload || typeof env.payload !== 'object') return null
  const p = { ...env.payload }
  delete p.uiSnapshot
  return p
}

function readAgentRunUiSnapshot (projectId, chatSessionId) {
  const snapEnv = readEnvelope(agentRunSnapshotKey(projectId, chatSessionId))
  if (snapEnv?.payload?.uiSnapshot != null) return snapEnv.payload.uiSnapshot
  const metaEnv = readEnvelope(agentRunKey(projectId, chatSessionId))
  return metaEnv?.payload?.uiSnapshot ?? null
}

export function getAgentRun (projectId, chatSessionId) {
  if (projectId == null || chatSessionId == null) return null
  const p = readAgentRunMetaPayload(projectId, chatSessionId)
  if (!p) return null
  return {
    runId: p.runId ?? null,
    messageId: p.messageId ?? null,
    clientMessageId: p.clientMessageId ?? null,
    status: p.status ?? 'idle',
    startedAt: p.startedAt ?? null,
    updatedAt: p.updatedAt ?? null,
    lastSeq: Number(p.lastSeq) || 0,
    llmModel: p.llmModel ?? null,
    uiSnapshot: readAgentRunUiSnapshot(projectId, chatSessionId)
  }
}

/** 仅更新续流指针（小 payload，不读写 uiSnapshot 分键） */
export function patchAgentRunSeq (projectId, chatSessionId, partial) {
  if (projectId == null || chatSessionId == null) return false
  const prev = readAgentRunMetaPayload(projectId, chatSessionId) || emptyAgentRunPayload()
  const now = Date.now()
  const { uiSnapshot: _drop, ...rest } = partial || {}
  const next = {
    ...prev,
    ...rest,
    updatedAt: partial?.updatedAt ?? now,
    startedAt:
      prev.startedAt ?? partial?.startedAt ?? (partial?.status === 'streaming' ? now : null)
  }
  if (next.status === 'idle' && !next.runId) {
    clearAgentRun(projectId, chatSessionId)
    return true
  }
  return writeEnvelope(agentRunKey(projectId, chatSessionId), next)
}

/** 节流写入 UI 快照（大对象单独键，不拖慢 lastSeq 写入） */
export function patchAgentRunSnapshot (projectId, chatSessionId, uiSnapshot) {
  if (projectId == null || chatSessionId == null) return false
  const key = agentRunSnapshotKey(projectId, chatSessionId)
  if (uiSnapshot == null) {
    try {
      sessionStorage.removeItem(key)
    } catch (e) {
      console.warn('[bcdSessionStore] clear agent snapshot failed', e)
    }
    return true
  }
  return writeEnvelope(key, { uiSnapshot })
}

export function patchAgentRun (projectId, chatSessionId, partial) {
  if (projectId == null || chatSessionId == null) return false
  const { uiSnapshot, ...metaPartial } = partial || {}
  let ok = true
  if (Object.keys(metaPartial).length > 0) {
    ok = patchAgentRunSeq(projectId, chatSessionId, metaPartial)
  }
  if (partial && Object.prototype.hasOwnProperty.call(partial, 'uiSnapshot')) {
    patchAgentRunSnapshot(projectId, chatSessionId, uiSnapshot ?? null)
  }
  return ok
}

export function clearAgentRun (projectId, chatSessionId) {
  try {
    sessionStorage.removeItem(agentRunKey(projectId, chatSessionId))
    sessionStorage.removeItem(agentRunSnapshotKey(projectId, chatSessionId))
  } catch (e) {
    console.warn('[bcdSessionStore] clear agent run failed', e)
  }
}

/** 超过该毫秒未更新则标 stale（后端仍 running 时仍可续流） */
export const AGENT_RUN_STALE_MS = 120000

export function awaitingMessageIdsFromHeld (heldMap) {
  const ids = new Set()
  if (!heldMap || typeof heldMap !== 'object') return []
  for (const h of Object.values(heldMap)) {
    if (h?.messageId != null && h.messageId !== '') ids.add(String(h.messageId))
  }
  return [...ids]
}

// —— 工作台 Tab 索引与 Tab 文档（§Tab级sessionStorage方案 M0/M1） ——

/** 从 localStorage user 解析 id，避免同机换号串 Tab 缓存 */
export function resolveBcdUserId () {
  try {
    const raw = localStorage.getItem('user')
    if (!raw) return '0'
    const u = JSON.parse(raw)
    const id = u?.id ?? u?.user_id ?? u?.userId
    return id != null && id !== '' ? String(id) : '0'
  } catch {
    return '0'
  }
}

const emptyTabIndexPayload = () => ({
  activeWorkbenchTabId: null,
  tabs: []
})

export function getTabIndex (userId, projectId) {
  const env = readEnvelope(tabIndexKey(userId, projectId))
  if (!env?.payload || typeof env.payload !== 'object') return emptyTabIndexPayload()
  const p = env.payload
  return {
    activeWorkbenchTabId: p.activeWorkbenchTabId ?? null,
    tabs: Array.isArray(p.tabs) ? p.tabs : []
  }
}

/**
 * @param {string} userId
 * @param {string|number} projectId
 * @param {Array<{ id, kind, title?, meta? }>} tabs
 * @param {string|null} activeWorkbenchTabId
 */
export function flushTabIndex (userId, projectId, tabs, activeWorkbenchTabId) {
  if (userId == null || projectId == null || projectId === '') return false
  const slim = (Array.isArray(tabs) ? tabs : []).map((t) => ({
    id: t.id,
    kind: t.kind,
    title: t.title,
    meta: t.meta && typeof t.meta === 'object' ? { ...t.meta } : {}
  }))
  evictTabDocsLRU(
    userId,
    projectId,
    slim.map((t) => t.id).filter(Boolean)
  )
  return writeEnvelope(tabIndexKey(userId, projectId), {
    activeWorkbenchTabId: activeWorkbenchTabId ?? null,
    tabs: slim
  })
}

export function clearTabIndex (userId, projectId) {
  try {
    sessionStorage.removeItem(tabIndexKey(userId, projectId))
  } catch {
    /* ignore */
  }
}

const emptyTabDocPayload = () => ({
  tabId: null,
  kind: null,
  scope: {},
  view: {},
  working: {},
  fieldDrafts: null,
  listSnapshot: null
})

export function getTabDocument (userId, projectId, workbenchTabId) {
  const env = readEnvelope(tabDocKey(userId, projectId, workbenchTabId))
  if (!env?.payload || typeof env.payload !== 'object') return emptyTabDocPayload()
  const p = env.payload
  return {
    tabId: p.tabId ?? workbenchTabId,
    kind: p.kind ?? null,
    scope: p.scope && typeof p.scope === 'object' ? { ...p.scope } : {},
    view: p.view && typeof p.view === 'object' ? { ...p.view } : {},
    working:
      p.working && typeof p.working === 'object' ? { ...p.working } : {},
    fieldDrafts:
      p.fieldDrafts && typeof p.fieldDrafts === 'object' ? { ...p.fieldDrafts } : null,
    listSnapshot:
      p.listSnapshot && typeof p.listSnapshot === 'object' ? { ...p.listSnapshot } : null
  }
}

export function patchTabDocument (userId, projectId, workbenchTabId, partial) {
  if (userId == null || projectId == null || !workbenchTabId) return false
  const prev = getTabDocument(userId, projectId, workbenchTabId)
  const key = tabDocKey(userId, projectId, workbenchTabId)
  touchTabDocKey(key)
  const next = { ...prev, ...partial, tabId: workbenchTabId }
  const raw = JSON.stringify({
    schemaVersion: SCHEMA_VERSION,
    updatedAt: Date.now(),
    payload: next
  })
  if (raw.length > TAB_DOC_SOFT_MAX_BYTES) {
    return writeEnvelope(key, next, { allowShrink: true })
  }
  return writeEnvelope(key, next)
}

export function patchTabDocListSnapshot (userId, projectId, workbenchTabId, listSnapshot) {
  return patchTabDocument(userId, projectId, workbenchTabId, {
    listSnapshot: listSnapshot || null
  })
}

export function patchTabDocFieldDrafts (userId, projectId, workbenchTabId, fieldDrafts) {
  if (!fieldDrafts || typeof fieldDrafts !== 'object') return false
  return patchTabDocument(userId, projectId, workbenchTabId, { fieldDrafts })
}

export function clearTabDocFieldDrafts (userId, projectId, workbenchTabId) {
  return patchTabDocument(userId, projectId, workbenchTabId, { fieldDrafts: null })
}

export function patchTabDocWorking (userId, projectId, workbenchTabId, recordKey, slot) {
  if (!recordKey) return false
  const prev = getTabDocument(userId, projectId, workbenchTabId)
  const working = { ...prev.working, [String(recordKey)]: { ...slot, cachedAt: Date.now() } }
  return patchTabDocument(userId, projectId, workbenchTabId, { working })
}

export function clearTabDocWorking (userId, projectId, recordKey) {
  if (userId == null || projectId == null || !recordKey) return
  const prefix = `${BCD_SS_PREFIX}tabdoc:${String(userId)}:${String(projectId)}:`
  const rk = String(recordKey)
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const k = sessionStorage.key(i)
      if (!k || !k.startsWith(prefix)) continue
      const env = readEnvelope(k)
      if (!env?.payload?.working) continue
      const working = { ...env.payload.working }
      if (!working[rk]) continue
      delete working[rk]
      const next = { ...env.payload, working }
      if (Object.keys(working).length === 0) {
        sessionStorage.removeItem(k)
      } else {
        writeEnvelope(k, next)
      }
    }
  } catch (e) {
    console.warn('[bcdSessionStore] clearTabDocWorking failed', e)
  }
}

/** 与 GET diff-reviews pending 对齐：删掉各 Tab 文档中已无 pending 的 working 槽 */
export function reconcileTabDocs (userId, projectId, pendingKeys) {
  if (userId == null || projectId == null) return
  const allowed = new Set((pendingKeys || []).map((k) => String(k)))
  const prefix = `${BCD_SS_PREFIX}tabdoc:${String(userId)}:${String(projectId)}:`
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i)
      if (!k || !k.startsWith(prefix)) continue
      const env = readEnvelope(k)
      if (!env?.payload?.working) continue
      const working = { ...env.payload.working }
      let changed = false
      for (const wk of Object.keys(working)) {
        if (!allowed.has(wk)) {
          delete working[wk]
          changed = true
        }
      }
      if (!changed) continue
      if (Object.keys(working).length === 0) {
        sessionStorage.removeItem(k)
      } else {
        writeEnvelope(k, { ...env.payload, working })
      }
    }
  } catch (e) {
    console.warn('[bcdSessionStore] reconcileTabDocs failed', e)
  }
}

// —— 调试 ——

export function dumpAll () {
  let debug = false
  try {
    debug = localStorage.getItem('bcd:ss:debug') === '1'
  } catch {
    debug = false
  }
  if (!debug && typeof import.meta !== 'undefined' && !import.meta.env?.DEV) {
    return []
  }
  const rows = []
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i)
      if (k && k.startsWith(BCD_SS_PREFIX)) {
        rows.push({ key: k, bytes: (sessionStorage.getItem(k) || '').length })
      }
    }
  } catch (e) {
    console.warn('[bcdSessionStore] dumpAll failed', e)
  }
  if (rows.length && (debug || import.meta.env?.DEV)) {
    console.table(rows)
    const tabdocs = rows.filter((r) => r.key.includes(':tabdoc:'))
    if (tabdocs.length) {
      console.table(
        tabdocs.map((r) => ({
          tab: r.key.split(':').slice(-1)[0],
          kb: (r.bytes / 1024).toFixed(1)
        }))
      )
    }
  }
  return rows
}
