/**
 * 新建预览「已采纳」稳定键：同一项目 + 目标类型 + 标题 + 计划 视为同一条逻辑记录，
 * 用于避免重复展示待确认行 / 重复新建预览，改为跳转到已创建行。
 */
export const STABLE_CREATE_LS_PREFIX = 'badcase_doctor:stable_created:'

export function makeStableCreateKey (projectId, target, preview) {
  const pid = projectId != null && projectId !== '' ? String(projectId) : ''
  const t = (target || 'testcase').toString()
  const p = preview || {}
  const title = (
    p.title ||
    p.name ||
    p.bug_title ||
    p.bugTitle ||
    p.testcase_title ||
    p.badcase_title ||
    ''
  ).toString().trim()
  const planId = p.plan_id ?? p.planId ?? 'null'
  return `${pid}|${t}|${title}|${planId}`
}

export function getStableCreatedId (projectId, target, preview) {
  if (projectId == null || projectId === '') return null
  const key = makeStableCreateKey(projectId, target, preview)
  const storageKey = `${STABLE_CREATE_LS_PREFIX}${projectId}`
  try {
    const raw = localStorage.getItem(storageKey)
    const obj = raw ? JSON.parse(raw) : {}
    const entry = obj[key]
    if (entry && typeof entry === 'object' && entry.createdId != null) {
      const id = Number(entry.createdId)
      return Number.isFinite(id) ? id : null
    }
    if (typeof entry === 'number' && Number.isFinite(entry)) return entry
  } catch (e) {
    console.warn('[CREATE] getStableCreatedId 读取失败', e)
  }
  return null
}

export function persistStableCreatedId (projectId, target, preview, createdId) {
  if (projectId == null || projectId === '' || createdId == null) return
  const key = makeStableCreateKey(projectId, target, preview)
  const storageKey = `${STABLE_CREATE_LS_PREFIX}${projectId}`
  try {
    const raw = localStorage.getItem(storageKey)
    const obj = raw ? JSON.parse(raw) : {}
    obj[key] = { createdId: Number(createdId), updatedAt: Date.now() }
    localStorage.setItem(storageKey, JSON.stringify(obj))
  } catch (e) {
    console.warn('[CREATE] persistStableCreatedId 失败', e)
  }
}
