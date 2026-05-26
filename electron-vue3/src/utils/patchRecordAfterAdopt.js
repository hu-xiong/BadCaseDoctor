/**
 * 采纳后用服务端实体或单条 GET 刷新列表/卡片行（§6.1），避免整表 fetchCards。
 */

export function sameRecordId (a, b) {
  if (a == null || b == null) return false
  return String(a) === String(b)
}

export function normalizeAdoptTargetType (t) {
  const x = String(t || 'bug')
    .toLowerCase()
    .replace(/-/g, '_')
  if (x === 'test_case') return 'testcase'
  return x
}

/**
 * @param {string} targetType
 * @param {string|number} recordId
 * @param {{ getBugDetail, getBadcaseDetail, getTestCaseDetail, getCardDetail }} api
 */
export async function fetchAdoptedRecordRow (targetType, recordId, api) {
  const id = String(recordId ?? '').trim()
  if (!id || !/^\d+$/.test(id)) return null
  const nt = normalizeAdoptTargetType(targetType)
  try {
    if (nt === 'bug') {
      const res = await api.getBugDetail(id)
      return res?.data?.success ? res.data.bug : null
    }
    if (nt === 'badcase' || nt === 'bad_case') {
      const res = await api.getBadcaseDetail(id)
      return res?.data?.success ? res.data.badcase : null
    }
    if (nt === 'testcase') {
      const res = await api.getTestCaseDetail(id)
      const row = res?.data?.testcase ?? res?.data?.test_case
      return res?.data?.success ? row : null
    }
    if (nt === 'card') {
      const res = await api.getCardDetail(id)
      const row = res?.data?.card ?? res?.data
      return res?.data?.success !== false && row && typeof row === 'object' ? row : null
    }
  } catch (e) {
    console.warn('[patchRecordAfterAdopt] fetch failed', nt, id, e)
  }
  return null
}

/**
 * @param {object} row
 * @param {string} targetType
 * @param {{ badcases?, filteredBadcases?, cards?, filteredCards? }} lists
 * @param {{ skipListTitleForBug?: boolean }} [opts] 仅 plan 卡片总表等场景可设 true；type-list Bug 行展示 bug.title 须合并
 */
export function mergeAdoptedRowIntoLists (row, targetType, lists, opts = {}) {
  if (!row || typeof row !== 'object') return false
  const nt = normalizeAdoptTargetType(targetType)
  const id = row.id
  if (id == null || id === '') return false
  const skipBugListTitle = opts.skipListTitleForBug === true

  if (nt === 'card') {
    let touched = false
    for (const arr of [lists.cards, lists.filteredCards]) {
      if (!Array.isArray(arr)) continue
      const i = arr.findIndex((c) => sameRecordId(c.id, id))
      if (i >= 0) {
        arr[i] = { ...arr[i], ...row }
        touched = true
      }
    }
    return touched
  }

  let touched = false
  const patch = { ...row }
  if (nt === 'bug' && skipBugListTitle) {
    delete patch.title
  }
  for (const arr of [lists.badcases, lists.filteredBadcases]) {
    if (!Array.isArray(arr)) continue
    const i = arr.findIndex((b) => sameRecordId(b.id, id))
    if (i >= 0) {
      arr[i] = { ...arr[i], ...patch }
      touched = true
    }
  }
  return touched
}

/**
 * @param {string} targetType
 * @param {string|number} recordId
 * @param {object|null} serverPayload modify 响应或含 adopted_entity 的对象
 * @param {{ getBugDetail, getBadcaseDetail, getTestCaseDetail, getCardDetail }} api
 * @param {{ badcases?, filteredBadcases?, cards?, filteredCards? }} lists
 */
function mergeAdoptedFieldsIntoRow (row, adoptedFields) {
  if (!row || typeof row !== 'object' || !adoptedFields || typeof adoptedFields !== 'object') {
    return row
  }
  return { ...row, ...adoptedFields }
}

export async function patchRecordAfterAdopt (
  targetType,
  recordId,
  serverPayload,
  api,
  lists,
  opts = {}
) {
  const partial = serverPayload?.adopted_fields
  const adoptAsync = serverPayload?.async === true

  /** 异步落库：仅用响应里的 adopted_fields / adopted_entity 补丁内存，禁止 GET 单条「落库再查」 */
  if (adoptAsync) {
    let row = serverPayload?.adopted_entity ?? null
    if (row && typeof row === 'object' && row.entity && typeof row.entity === 'object') {
      row = row.entity
    }
    if ((!row || typeof row !== 'object') && partial && typeof partial === 'object') {
      row = mergeAdoptedFieldsIntoRow({ id: recordId }, partial)
    } else if (row && typeof row === 'object' && partial && typeof partial === 'object') {
      row = mergeAdoptedFieldsIntoRow(row, partial)
    }
    if (!row || typeof row !== 'object') return null
    mergeAdoptedRowIntoLists(row, targetType, lists, opts)
    return row
  }

  let row = serverPayload?.adopted_entity ?? null
  if (row && typeof row === 'object' && row.entity && typeof row.entity === 'object') {
    row = row.entity
  }
  if ((!row || typeof row !== 'object') && partial && typeof partial === 'object') {
    row = mergeAdoptedFieldsIntoRow({ id: recordId }, partial)
  }
  if (!row || typeof row !== 'object') {
    row = await fetchAdoptedRecordRow(targetType, recordId, api)
  } else if (partial && typeof partial === 'object') {
    row = mergeAdoptedFieldsIntoRow(row, partial)
  }
  if (!row) return null
  mergeAdoptedRowIntoLists(row, targetType, lists, opts)
  return row
}
