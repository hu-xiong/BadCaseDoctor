/**
 * 采纳版本 / etag 对账（§6.1）：本地记录已采纳代数，避免 stale diff upsert 把黄条灌回。
 */

import { diffRecordKey } from './bcdSessionStore.js'

const SCHEMA = 1
const prefix = 'bcd:ss:adoptver:'

function adoptVersionsKey (userId, projectId) {
  return `${prefix}${String(userId)}:${String(projectId)}`
}

function readStore (userId, projectId) {
  try {
    const raw = sessionStorage.getItem(adoptVersionsKey(userId, projectId))
    if (!raw) return { versions: {} }
    const o = JSON.parse(raw)
    if (!o || typeof o !== 'object') return { versions: {} }
    if (o.schemaVersion != null && o.schemaVersion !== SCHEMA) return { versions: {} }
    const v = o.versions && typeof o.versions === 'object' ? o.versions : {}
    return { versions: { ...v } }
  } catch {
    return { versions: {} }
  }
}

function writeStore (userId, projectId, versions) {
  try {
    sessionStorage.setItem(
      adoptVersionsKey(userId, projectId),
      JSON.stringify({
        schemaVersion: SCHEMA,
        updatedAt: Date.now(),
        versions
      })
    )
    return true
  } catch (e) {
    console.warn('[recordAdoptVersion] write failed', e)
    return false
  }
}

/** @returns {string} 如 "3:2026-05-25T03:00:00" */
export function buildRecordVersionToken (lifecycleId, updatedAt) {
  const lc = lifecycleId != null && lifecycleId !== '' ? String(lifecycleId) : '0'
  const ts =
    updatedAt != null && String(updatedAt).trim() !== ''
      ? String(updatedAt).trim()
      : ''
  return `${lc}:${ts}`
}

export function buildRecordEtag (target, targetId, versionToken) {
  const nt = String(target || 'bug')
    .toLowerCase()
    .replace(/-/g, '_')
  const id = targetId != null && targetId !== '' ? String(targetId) : ''
  const v = versionToken != null ? String(versionToken) : ''
  return `W/"${nt}-${id}-${v}"`
}

/** pending / upsert 项 → version token */
export function pendingVersionFromDiffItem (item) {
  if (!item || typeof item !== 'object') return ''
  return buildRecordVersionToken(
    item.lifecycle_id ?? item.lifecycleId,
    item.updated_at ?? item.updatedAt
  )
}

/**
 * @returns {-1|0|1} a&lt;b / equal / a&gt;b；仅比较 lifecycle 与 updated_at 字符串
 */
export function compareRecordVersion (a, b) {
  const pa = String(a || '').split(':')
  const pb = String(b || '').split(':')
  const la = parseInt(pa[0], 10) || 0
  const lb = parseInt(pb[0], 10) || 0
  if (la !== lb) return la < lb ? -1 : 1
  const ta = pa.slice(1).join(':')
  const tb = pb.slice(1).join(':')
  if (ta === tb) return 0
  return ta < tb ? -1 : 1
}

export function getRecordAdoptVersion (userId, projectId, recordKey) {
  const { versions } = readStore(userId, projectId)
  return versions[String(recordKey)] || null
}

export function setRecordAdoptVersion (userId, projectId, recordKey, meta) {
  if (!recordKey) return
  const { versions } = readStore(userId, projectId)
  versions[String(recordKey)] = {
    version: meta?.version != null ? String(meta.version) : '',
    etag: meta?.etag != null ? String(meta.etag) : '',
    at: meta?.at != null ? Number(meta.at) : Date.now()
  }
  writeStore(userId, projectId, versions)
}

/** 已采纳版本 ≥ pending 版本 → 勿再把 pending 灌回列表 */
export function isPendingSupersededByAdopt (userId, projectId, recordKey, pendingVersion) {
  const pv = String(pendingVersion || '').trim()
  if (!pv) return false
  const adopted = getRecordAdoptVersion(userId, projectId, recordKey)
  const av = adopted?.version ? String(adopted.version) : ''
  if (!av) return false
  return compareRecordVersion(av, pv) >= 0
}

export function resolveAdoptVersionFromResponse (serverPayload, adoptedRow) {
  if (serverPayload?.adopt_version != null && String(serverPayload.adopt_version).trim()) {
    return String(serverPayload.adopt_version).trim()
  }
  const row = adoptedRow && typeof adoptedRow === 'object' ? adoptedRow : null
  if (row) {
    return buildRecordVersionToken(
      row.lifecycle_id ?? row.lifecycleId,
      row.updated_at ?? row.updatedAt
    )
  }
  const partial = serverPayload?.adopted_fields
  if (partial && typeof partial === 'object' && partial.updated_at) {
    return buildRecordVersionToken(0, partial.updated_at)
  }
  return ''
}

export function resolveEtagFromResponse (target, targetId, serverPayload, adoptedRow, versionToken) {
  if (serverPayload?.etag != null && String(serverPayload.etag).trim()) {
    return String(serverPayload.etag).trim()
  }
  const v =
    versionToken ||
    resolveAdoptVersionFromResponse(serverPayload, adoptedRow) ||
    ''
  if (v) return buildRecordEtag(target, targetId, v)
  return ''
}

export function commitAdoptVersionAfterSuccess (
  userId,
  projectId,
  targetType,
  recordId,
  serverPayload,
  adoptedRow
) {
  if (userId == null || projectId == null || recordId == null) return
  const key = diffRecordKey(targetType, recordId)
  const version = resolveAdoptVersionFromResponse(serverPayload, adoptedRow)
  const etag = resolveEtagFromResponse(targetType, recordId, serverPayload, adoptedRow, version)
  if (!version && !etag) return
  setRecordAdoptVersion(userId, projectId, key, { version, etag })
  if (typeof console !== 'undefined' && console.debug) {
    console.debug('[ADOPT-VERSION] commit', key, { version, etag })
  }
}

export { diffRecordKey }
