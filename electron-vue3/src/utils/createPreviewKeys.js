/**
 * 新建预览「已采纳」稳定键：同一项目 + 目标类型 + 标题 + 计划 视为同一条逻辑记录，
 * 用于避免重复展示待确认行 / 重复新建预览，改为跳转到已创建行。
 */
import { snowflakeIdStr } from './snowflakeId.js'

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
  return `${pid}|${t}|${title}|${planId}${copySeg}|k3`
}

function readStableCreateMap (projectId) {
  const storageKey = `${STABLE_CREATE_LS_PREFIX}${projectId}`
  try {
    const raw = localStorage.getItem(storageKey)
    return raw ? JSON.parse(raw) : {}
  } catch (e) {
    console.warn('[CREATE] readStableCreateMap 失败', e)
    return {}
  }
}

function writeStableCreateMap (projectId, obj) {
  const storageKey = `${STABLE_CREATE_LS_PREFIX}${projectId}`
  try {
    localStorage.setItem(storageKey, JSON.stringify(obj))
  } catch (e) {
    console.warn('[CREATE] writeStableCreateMap 失败', e)
  }
}

function entryCreatedId (entry) {
  if (entry == null) return ''
  if (typeof entry === 'object' && entry.createdId != null) {
    return snowflakeIdStr(entry.createdId) || String(entry.createdId).trim()
  }
  return snowflakeIdStr(entry) || String(entry).trim()
}

export function getStableCreatedId (projectId, target, preview) {
  if (projectId == null || projectId === '') return null
  const key = makeStableCreateKey(projectId, target, preview)
  const obj = readStableCreateMap(projectId)
  const id = entryCreatedId(obj[key])
  return id && /^\d+$/.test(id) ? id : null
}

export function persistStableCreatedId (projectId, target, preview, createdId) {
  if (projectId == null || projectId === '' || createdId == null) return
  const idStr = snowflakeIdStr(createdId) || String(createdId).trim()
  if (!idStr || !/^\d+$/.test(idStr)) return
  const key = makeStableCreateKey(projectId, target, preview)
  const obj = readStableCreateMap(projectId)
  obj[key] = { createdId: idStr, updatedAt: Date.now() }
  writeStableCreateMap(projectId, obj)
}

/** 记录已删除：按 createdId 清除 localStorage 中所有命中项，避免删后再建同名误显「已采纳」 */
export function clearStableCreatedIdByRecordId (projectId, createdId) {
  if (projectId == null || projectId === '' || createdId == null) return
  const want = snowflakeIdStr(createdId) || String(createdId).trim()
  if (!want || !/^\d+$/.test(want)) return
  const obj = readStableCreateMap(projectId)
  let changed = false
  for (const k of Object.keys(obj)) {
    if (entryCreatedId(obj[k]) === want) {
      delete obj[k]
      changed = true
    }
  }
  if (changed) writeStableCreateMap(projectId, obj)
}

export function clearStableCreateEntry (projectId, target, preview) {
  if (projectId == null || projectId === '') return
  const key = makeStableCreateKey(projectId, target, preview)
  const obj = readStableCreateMap(projectId)
  if (!Object.prototype.hasOwnProperty.call(obj, key)) return
  delete obj[key]
  writeStableCreateMap(projectId, obj)
}
