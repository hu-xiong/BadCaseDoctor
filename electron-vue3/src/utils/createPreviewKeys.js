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
  // 复制源不同则不应与「仅标题+计划相同」的旧记录共用一条稳定键，否则会误显「已创建」并跳到错误 id
  const copyHint =
    p.copy_from_card_id ??
    p.source_card_id ??
    p.copy_from_bug_id ??
    p.source_bug_id ??
    p.copy_from_badcase_id ??
    p.source_badcase_id ??
    p.copy_from_testcase_id ??
    p.source_testcase_id
  const copySeg =
    copyHint != null && String(copyHint).trim() !== ''
      ? `|copy:${String(copyHint).trim()}`
      : ''
  // k3：调整键规则时递增，避免沿用本地旧映射误命中已删或无关记录
  return `${pid}|${t}|${title}|${planId}${copySeg}|k3`
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
