/**
 * 工作台 Tab L3 内存缓存 + 与 tabdoc 的 listSnapshot / fieldDrafts 协作（M2+）
 */

/** @typedef {{ rows: object[], total: number, page: number, listKind?: string, fetchedAt: number }} ListSnapshot */

export const LIST_SNAPSHOT_MAX_ROWS = 80
const _memory = new Map()

export function getTabMemory (tabId) {
  if (!tabId) return null
  return _memory.get(String(tabId)) || null
}

export function setTabMemory (tabId, payload) {
  if (!tabId) return
  _memory.set(String(tabId), { ...payload, touchedAt: Date.now() })
}

export function deleteTabMemory (tabId) {
  if (tabId) _memory.delete(String(tabId))
}

export function clearProjectTabMemory (projectId) {
  const suffix = `:${String(projectId)}:`
  for (const k of [..._memory.keys()]) {
    if (k.includes(suffix) || !k.includes(':')) {
      /* tabId 不含 projectId；按 tabId 删在 closeWorkbenchTab */
    }
  }
}

/** 列表行瘦身，控制 sessionStorage 体积 */
export function slimListRow (row) {
  if (!row || typeof row !== 'object') return row
  const o = {
    id: row.id,
    title: row.title,
    status: row.status,
    assignee: row.assignee,
    assignee_id: row.assignee_id,
    plan_id: row.plan_id,
    card_id: row.card_id,
    created_at: row.created_at,
    updated_at: row.updated_at,
    priority: row.priority,
    bug_type: row.bug_type,
    source_id: row.source_id,
    type: row.type,
    remark: row.remark,
    description: row.description
  }
  if (row._pendingModify) o._pendingModify = row._pendingModify
  return o
}

export function snapshotListRows (rows, max = LIST_SNAPSHOT_MAX_ROWS) {
  const arr = Array.isArray(rows) ? rows : []
  return arr.slice(0, max).map(slimListRow)
}

/**
 * @param {object[]} rows
 * @returns {ListSnapshot}
 */
export function buildListSnapshot (rows, total, page, listKind) {
  return {
    rows: snapshotListRows(rows),
    total: Number(total) || 0,
    page: Number(page) || 1,
    listKind: listKind || null,
    fetchedAt: Date.now()
  }
}

/** Bug 详情表单快照（未采纳前的本地编辑） */
export function slimBugEntitySnapshot (bug) {
  if (!bug || typeof bug !== 'object') return null
  return {
    id: bug.id,
    title: bug.title,
    expected_result: bug.expected_result,
    actual_result: bug.actual_result,
    severity: bug.severity,
    priority: bug.priority,
    status: bug.status,
    case_category: bug.case_category,
    reproduction_steps: bug.reproduction_steps,
    assignee: Array.isArray(bug.assignee) ? [...bug.assignee] : bug.assignee,
    plan: bug.plan,
    project_id: bug.project_id,
    comment: bug.comment,
    attachments: bug.attachments
  }
}

export function isListSnapshotFresh (snap, maxAgeMs = 120000) {
  if (!snap || !snap.fetchedAt) return false
  return Date.now() - Number(snap.fetchedAt) < maxAgeMs
}
