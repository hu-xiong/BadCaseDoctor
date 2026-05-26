/**
 * 工作台 Tab 视图 dehydrate/hydrate（对齐 Tab级sessionStorage 方案 M0/M1）
 */

import {
  getTabDocument,
  patchTabDocument,
  patchTabDocWorking,
  patchTabDocListSnapshot,
  patchTabDocFieldDrafts,
  diffRecordKey
} from './bcdSessionStore.js'
import { buildListSnapshot } from './workbenchTabDataCache.js'

/** @param {HTMLElement|null} root */
export function readListScrollTop (root) {
  if (!root || typeof root.querySelector !== 'function') return 0
  const body = root.querySelector('.table-body')
  return body && typeof body.scrollTop === 'number' ? body.scrollTop : 0
}

/** @param {HTMLElement|null} root */
export function writeListScrollTop (root, scrollTop) {
  if (!root || typeof root.querySelector !== 'function') return
  const body = root.querySelector('.table-body')
  if (!body) return
  const top = Number(scrollTop) || 0
  requestAnimationFrame(() => {
    body.scrollTop = top
  })
}

/**
 * @param {object} ctx
 * @param {import('vue').Ref|string} ctx.searchText
 * @param {import('vue').Ref|string} ctx.selectedAssignee
 * @param {import('vue').Ref|string} ctx.selectedStatus
 * @param {import('vue').Ref|number} ctx.badcasePage
 * @param {import('vue').Ref|number} ctx.cardPage
 * @param {import('vue').Ref|string|null} ctx.highlightRowId
 * @param {import('vue').Ref|string|null} ctx.currentTypeFilter
 * @param {HTMLElement|null} ctx.listRootEl
 */
export function captureWorkbenchViewState (ctx) {
  const st = (r) => (r && typeof r === 'object' && 'value' in r ? r.value : r)
  return {
    searchKeyword: String(st(ctx.searchText) ?? ''),
    selectedAssignee: String(st(ctx.selectedAssignee) ?? ''),
    selectedStatus: String(st(ctx.selectedStatus) ?? ''),
    badcasePage: Number(st(ctx.badcasePage)) || 1,
    cardPage: Number(st(ctx.cardPage)) || 1,
    highlightRowId:
      st(ctx.highlightRowId) != null && st(ctx.highlightRowId) !== ''
        ? String(st(ctx.highlightRowId))
        : null,
    listContentType: st(ctx.currentTypeFilter) != null ? String(st(ctx.currentTypeFilter)) : null,
    scrollTop: readListScrollTop(ctx.listRootEl)
  }
}

export function applyWorkbenchViewState (ctx, view) {
  if (!view || typeof view !== 'object') return
  const set = (r, v) => {
    if (r && typeof r === 'object' && 'value' in r) r.value = v
  }
  if (view.searchKeyword != null) set(ctx.searchText, String(view.searchKeyword))
  if (view.selectedAssignee != null) set(ctx.selectedAssignee, String(view.selectedAssignee))
  if (view.selectedStatus != null) set(ctx.selectedStatus, String(view.selectedStatus))
  if (view.badcasePage != null) set(ctx.badcasePage, Number(view.badcasePage) || 1)
  if (view.cardPage != null) set(ctx.cardPage, Number(view.cardPage) || 1)
  if (view.highlightRowId != null) set(ctx.highlightRowId, view.highlightRowId)
  writeListScrollTop(ctx.listRootEl, view.scrollTop)
}

export function buildTabScopeFromMeta (tab, projectId) {
  const meta = tab?.meta || {}
  return {
    projectId: projectId != null ? Number(projectId) || projectId : null,
    planId: meta.planId ?? meta.plan_id ?? null,
    cardId: meta.cardId ?? meta.card_id ?? null,
    target: meta.type ?? meta.target ?? null,
    targetId: meta.entityId ?? meta.target_id ?? null
  }
}

/** pendingModifications 单条 → working mirror（不含 _ 前缀内部键的完整 modify 对象） */
export function modificationsMirrorFromPending (modifyData) {
  if (!modifyData || typeof modifyData !== 'object') return {}
  const out = {}
  for (const [k, v] of Object.entries(modifyData)) {
    if (String(k).startsWith('_')) continue
    out[k] = v
  }
  return out
}

/**
 * 将当前 Tab 的 pending 写入 tabdoc.working（与 pendingModifications 双写）
 */
export function syncTabWorkingFromPendingMap ({
  userId,
  projectId,
  workbenchTabId,
  tabKind,
  tabScope,
  pendingMap,
  sessionId
}) {
  if (!userId || !projectId || !workbenchTabId) return
  patchTabDocument(userId, projectId, workbenchTabId, {
    kind: tabKind ?? null,
    scope: tabScope || {}
  })
  const pm = pendingMap && typeof pendingMap === 'object' ? pendingMap : {}
  for (const [recordKey, modifyData] of Object.entries(pm)) {
    if (!modifyData || typeof modifyData !== 'object') continue
    const target = modifyData._target || 'bug'
    const tid = String(recordKey)
    if (!tid || !/^\d+$/.test(tid)) continue
    const rk = diffRecordKey(target, tid)
    patchTabDocWorking(userId, projectId, workbenchTabId, rk, {
      target,
      targetId: tid,
      status: 'pending',
      lifecycleId: modifyData._lifecycleId ?? null,
      diffFingerprint: modifyData._diffFingerprint ?? null,
      modificationsMirror: modificationsMirrorFromPending(modifyData),
      sourceSessionId: sessionId != null ? String(sessionId) : modifyData._sessionId ?? null,
      messageId: modifyData._messageId ?? null
    })
  }
}

export function dehydrateWorkbenchTabView ({
  userId,
  projectId,
  workbenchTabId,
  tabKind,
  tabScope,
  viewCtx,
  listRows,
  listTotal,
  listPage,
  listKind,
  fieldDrafts
}) {
  if (!userId || !projectId || !workbenchTabId) return false
  const view = captureWorkbenchViewState(viewCtx)
  const partial = {
    kind: tabKind ?? null,
    scope: tabScope || {},
    view
  }
  if (Array.isArray(listRows) && listRows.length > 0) {
    partial.listSnapshot = buildListSnapshot(listRows, listTotal, listPage, listKind)
  }
  if (fieldDrafts && typeof fieldDrafts === 'object') {
    partial.fieldDrafts = fieldDrafts
  }
  return patchTabDocument(userId, projectId, workbenchTabId, partial)
}

export function hydrateWorkbenchTabView (userId, projectId, workbenchTabId, viewCtx) {
  if (!userId || !projectId || !workbenchTabId) return null
  const doc = getTabDocument(userId, projectId, workbenchTabId)
  if (doc.view && Object.keys(doc.view).length) {
    applyWorkbenchViewState(viewCtx, doc.view)
  }
  return doc
}

/** 从 tabdoc 读取列表快照（配合 L3 内存缓存） */
export function getTabListSnapshotFromDoc (userId, projectId, workbenchTabId) {
  const doc = getTabDocument(userId, projectId, workbenchTabId)
  return doc.listSnapshot || null
}

export function getTabFieldDraftsFromDoc (userId, projectId, workbenchTabId) {
  const doc = getTabDocument(userId, projectId, workbenchTabId)
  return doc.fieldDrafts || null
}

export function persistTabListSnapshot (userId, projectId, workbenchTabId, snapshot) {
  if (!userId || !projectId || !workbenchTabId || !snapshot) return false
  return patchTabDocListSnapshot(userId, projectId, workbenchTabId, snapshot)
}

export function persistTabFieldDrafts (userId, projectId, workbenchTabId, fieldDrafts) {
  if (!userId || !projectId || !workbenchTabId) return false
  return patchTabDocFieldDrafts(userId, projectId, workbenchTabId, fieldDrafts)
}
