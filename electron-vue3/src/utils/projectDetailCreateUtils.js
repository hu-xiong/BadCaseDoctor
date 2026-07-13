/** ProjectDetail 新建预览/待确认行工具（自 ProjectDetail.vue 拆出） */

const PROCESSED_CREATE_KEY_LS_PREFIX = 'badcase_doctor:processed_create_key:'

export function getProcessedCreateKeyStorageKey(pid) {
  return `${PROCESSED_CREATE_KEY_LS_PREFIX}${String(pid)}`
}

export function normalizeCreateTarget(t) {
  const s = (t || '').toString().toLowerCase()
  if (s === 'testcase' || s === 'test_case') return 'test_case'
  if (s === 'bug') return 'bug'
  if (s === 'badcase') return 'badcase'
  if (s === 'card') return 'card'
  if (s === 'plan') return 'plan'
  return s
}

export function inferCreateTargetFromPreview(pv, explicit) {
  const ex0 =
    explicit != null && String(explicit).trim() !== ''
      ? String(explicit).trim().toLowerCase()
      : ''
  if (ex0 === 'card') return 'card'
  if (ex0 === 'plan') return 'plan'
  if (ex0 === 'test_case') return 'testcase'
  if (['bug', 'badcase', 'testcase'].includes(ex0)) return ex0

  if (pv && typeof pv === 'object') {
    if (pv.copy_from_card_id != null && String(pv.copy_from_card_id).trim() !== '') return 'card'
    if (pv.source_card_id != null && String(pv.source_card_id).trim() !== '') return 'card'
    if (pv.copy_from_bug_id != null && String(pv.copy_from_bug_id).trim() !== '') return 'bug'
    if (pv.source_bug_id != null && String(pv.source_bug_id).trim() !== '') return 'bug'
    if (pv.copy_from_badcase_id != null || pv.source_badcase_id != null) return 'badcase'
    if (pv.copy_from_testcase_id != null || pv.source_testcase_id != null) return 'testcase'
    if (
      pv.severity != null ||
      pv.bug_type != null ||
      (pv.steps_to_reproduce != null && String(pv.steps_to_reproduce).trim() !== '') ||
      (pv.reproduce_steps != null && String(pv.reproduce_steps).trim() !== '')
    ) {
      return 'bug'
    }
    if (pv.case_category != null || (pv.base_problem != null && String(pv.base_problem).trim() !== '')) {
      return 'badcase'
    }
    if (pv.steps != null || (pv.case_type != null && String(pv.case_type).trim() !== '')) {
      return 'testcase'
    }
    if (
      (pv.name != null && String(pv.name).trim() !== '') &&
      !pv.title &&
      !pv.steps_to_reproduce &&
      !pv.reproduction_steps
    ) {
      return 'plan'
    }
    if (pv.start_date != null && pv.end_date != null && !pv.title && !pv.steps) {
      return 'plan'
    }
  }
  return 'bug'
}

export function makeCreateKeyFactory(createSessionId) {
  return (target, preview, messageId = null) => {
    const t = target || 'testcase'
    const p = preview || {}
    const title = (
      p.title ||
      p.name ||
      p.bug_title ||
      p.bugTitle ||
      p.testcase_title ||
      p.badcase_title ||
      ''
    )
      .toString()
      .trim()
    const planId = p.plan_id ?? p.planId ?? null
    const scope = (messageId ?? p._messageId ?? p.messageId) ?? `session:${createSessionId}`
    return `${scope}|${t}|${title}|${planId ?? 'null'}`
  }
}

export function loadProcessedCreateFromStorage(pid, processedCreateKeyMap, createdIdByCreateKey) {
  if (!pid && pid !== 0) return
  const raw = localStorage.getItem(getProcessedCreateKeyStorageKey(pid))
  try {
    const obj = raw ? JSON.parse(raw) || {} : {}
    Object.keys(obj).forEach((createKey) => {
      if (!createKey) return
      processedCreateKeyMap[createKey] = true
      const meta = obj[createKey]
      if (meta && typeof meta === 'object' && meta.createdId) {
        createdIdByCreateKey[createKey] = meta.createdId
      }
    })
  } catch (e) {
    console.warn('[CREATE] 载入 processed create key 失败:', e)
  }
}

export function persistProcessedCreateKey(pid, createKey, meta = {}) {
  if (!pid && pid !== 0) return
  if (!createKey) return
  const storageKey = getProcessedCreateKeyStorageKey(pid)
  let obj = {}
  try {
    const raw = localStorage.getItem(storageKey)
    obj = raw ? JSON.parse(raw) || {} : {}
  } catch {
    obj = {}
  }
  obj[createKey] = {
    processed: true,
    ...(obj[createKey] && typeof obj[createKey] === 'object' ? obj[createKey] : {}),
    ...(meta && typeof meta === 'object' ? meta : {})
  }
  try {
    localStorage.setItem(storageKey, JSON.stringify(obj))
  } catch (e) {
    console.warn('[CREATE] persist processed create key 失败:', e)
  }
}

export function stripNavOnlyCreatePreview(p) {
  const o = { ...(p || {}) }
  delete o.copy_from_bug_id
  delete o.source_bug_id
  delete o.copy_from_badcase_id
  delete o.source_badcase_id
  delete o.copy_from_testcase_id
  delete o.source_testcase_id
  delete o.copy_from_card_id
  delete o.source_card_id
  delete o.nav_copy_source_card_id
  delete o.navCopySourceCardId
  return o
}

export function uniqPreserveOrderStringIds(arr) {
  const seen = new Set()
  const out = []
  for (const x of arr || []) {
    const s = x == null ? '' : String(x)
    if (!s || seen.has(s)) continue
    seen.add(s)
    out.push(s)
  }
  return out
}
