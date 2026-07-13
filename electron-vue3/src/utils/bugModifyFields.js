/**
 * Bug modify / 沙箱 / 详情 diff：复现步骤等字段与后端 steps_to_reproduce 对齐。
 */
import { stripHtmlForModifyDisplay } from './testcaseModifyFields.js'

export const BUG_REPRODUCTION_STEP_KEYS = [
  'steps_to_reproduce',
  'reproduction_steps',
  'reproduce_steps'
]

/** Agent/LLM 可能误用测例字段名 steps 或 reproduce_steps，统一落到 steps_to_reproduce */
export const BUG_REPRO_PENDING_ALIASES = [
  'reproduction_steps',
  'reproduce_steps',
  'repro_steps',
  'steps'
]

/** 将 pendingDiff.modifications 中复现步骤别名合并为 steps_to_reproduce（原地修改） */
export function normalizeBugPendingReproMods(mods) {
  if (!mods || typeof mods !== 'object') return mods
  const canonical = 'steps_to_reproduce'
  let srcKey = null
  for (const k of [canonical, ...BUG_REPRO_PENDING_ALIASES]) {
    if (mods[k] && typeof mods[k] === 'object' && ('old' in mods[k] || 'new' in mods[k])) {
      srcKey = k
      break
    }
  }
  if (!srcKey || srcKey === canonical) return mods
  if (!mods[canonical]) {
    mods[canonical] = mods[srcKey]
  } else {
    const cur = mods[canonical]
    const incoming = mods[srcKey]
    if (incoming && typeof incoming === 'object') {
      if (!('old' in cur) && 'old' in incoming) cur.old = incoming.old
      if (!('new' in cur) && 'new' in incoming) cur.new = incoming.new
    }
  }
  for (const k of BUG_REPRO_PENDING_ALIASES) {
    delete mods[k]
  }
  return mods
}

/** 从 modify 沙箱 before/after 行读取复现步骤原文 */
export function readBugReproductionStepsFromRow(row) {
  if (!row || typeof row !== 'object') return ''
  for (const k of BUG_REPRODUCTION_STEP_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(row, k)) continue
    const v = row[k]
    if (v == null) continue
    if (typeof v === 'string' && v.trim() === '') continue
    return typeof v === 'string' ? v : String(v)
  }
  return ''
}

export function formatBugReproductionStepsForDisplay(raw) {
  const s = readBugReproductionStepsFromRow(
    typeof raw === 'string' || typeof raw === 'number' ? { steps_to_reproduce: raw } : raw
  )
  if (!s) return ''
  return stripHtmlForModifyDisplay(s) || s.trim()
}

/** Bug 期望结果：库列 expected_result；Agent 可能用 expected / 中文标签 */
export const BUG_EXPECTED_RESULT_KEYS = ['expected_result', 'expected']

export const BUG_EXPECTED_PENDING_ALIASES = ['expected', '预期结果', '期望结果']

export function readBugExpectedResultFromRow(row) {
  if (!row || typeof row !== 'object') return ''
  for (const k of BUG_EXPECTED_RESULT_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(row, k)) continue
    const v = row[k]
    if (v == null) continue
    if (typeof v === 'string' && v.trim() === '') continue
    return typeof v === 'string' ? v : String(v)
  }
  return ''
}

export function formatBugExpectedResultForDisplay(raw) {
  const s = readBugExpectedResultFromRow(
    typeof raw === 'string' || typeof raw === 'number' ? { expected_result: raw } : raw
  )
  if (!s) return ''
  return stripHtmlForModifyDisplay(s) || s.trim()
}

/** pendingDiff.modifications 中期望结果别名合并为 expected_result */
export function normalizeBugPendingExpectedMods(mods) {
  if (!mods || typeof mods !== 'object') return mods
  const canonical = 'expected_result'
  let srcKey = null
  for (const k of [canonical, ...BUG_EXPECTED_PENDING_ALIASES]) {
    if (mods[k] && typeof mods[k] === 'object' && ('old' in mods[k] || 'new' in mods[k])) {
      srcKey = k
      break
    }
  }
  if (!srcKey || srcKey === canonical) return mods
  if (!mods[canonical]) {
    mods[canonical] = mods[srcKey]
  } else {
    const cur = mods[canonical]
    const incoming = mods[srcKey]
    if (incoming && typeof incoming === 'object') {
      if (!('old' in cur) && 'old' in incoming) cur.old = incoming.old
      if (!('new' in cur) && 'new' in incoming) cur.new = incoming.new
    }
  }
  for (const k of BUG_EXPECTED_PENDING_ALIASES) {
    delete mods[k]
  }
  return mods
}

const BUG_SANDBOX_DETAIL_FIELDS = ['steps_to_reproduce', 'expected_result', 'actual_result']

function bugSandboxFieldValuesEqual(field, beforeVal, afterVal) {
  if (field === 'steps_to_reproduce') {
    return (
      formatBugReproductionStepsForDisplay(beforeVal) ===
      formatBugReproductionStepsForDisplay(afterVal)
    )
  }
  return (
    formatBugExpectedResultForDisplay(beforeVal) ===
    formatBugExpectedResultForDisplay(afterVal)
  )
}

function readBugSandboxFieldRaw(row, field) {
  if (field === 'steps_to_reproduce') return readBugReproductionStepsFromRow(row)
  if (field === 'expected_result') return readBugExpectedResultFromRow(row)
  if (field === 'actual_result') {
    if (!row || typeof row !== 'object') return ''
    const v = row.actual_result
    return v != null && String(v).trim() !== '' ? String(v) : ''
  }
  return ''
}

function formatBugSandboxFieldDisplay(field, raw) {
  if (field === 'steps_to_reproduce') return formatBugReproductionStepsForDisplay(raw)
  if (field === 'expected_result') return formatBugExpectedResultForDisplay(raw)
  if (field === 'actual_result') return formatBugExpectedResultForDisplay(raw)
  return raw != null ? String(raw).trim() : ''
}

function readBugModSide(mods, field, which) {
  if (!mods || typeof mods !== 'object') return undefined
  const keys = new Set([field, ...BUG_EXPECTED_PENDING_ALIASES, 'expected', 'actual'])
  if (field === 'steps_to_reproduce') {
    BUG_REPRO_PENDING_ALIASES.forEach((k) => keys.add(k))
  }
  for (const mk of keys) {
    const m = mods[mk]
    if (m && typeof m === 'object' && (which === 'old' ? 'old' in m : 'new' in m)) {
      return which === 'old' ? m.old : m.new
    }
  }
  return undefined
}

function normalizeBugSandboxFieldKey(field, fieldLabel) {
  const f = String(field || '')
    .trim()
    .toLowerCase()
  const lab = String(fieldLabel || '').trim()
  if (
    f === 'expected_result' ||
    f === 'expected' ||
    lab === '期望结果' ||
    lab === '预期结果' ||
    (lab.includes('期望') && lab.includes('结果')) ||
    (lab.includes('预期') && lab.includes('结果'))
  ) {
    return 'expected_result'
  }
  if (f === 'actual_result' || lab === '实际结果' || (lab.includes('实际') && lab.includes('结果'))) {
    return 'actual_result'
  }
  if (
    f === 'steps_to_reproduce' ||
    BUG_REPRO_PENDING_ALIASES.includes(f) ||
    f === 'steps' ||
    lab.includes('复现步骤')
  ) {
    return 'steps_to_reproduce'
  }
  if (BUG_SANDBOX_DETAIL_FIELDS.includes(f)) return f
  return f || null
}

/** modifications 的 key 是否属于本次 Bug 详情字段变更 */
function bugModKeysForSandboxField(field) {
  if (field === 'expected_result') return [field, ...BUG_EXPECTED_PENDING_ALIASES, 'expected']
  if (field === 'steps_to_reproduce') return [field, ...BUG_REPRO_PENDING_ALIASES, 'steps']
  if (field === 'actual_result') return [field, 'actual']
  return [field]
}

function collectBugSandboxPreviewFieldKeys(baseRows, mods) {
  const keys = new Set()
  for (const r of baseRows || []) {
    const fk = normalizeBugSandboxFieldKey(r?.field, r?.field_label)
    if (fk) keys.add(fk)
  }
  if (mods && typeof mods === 'object') {
    for (const rawKey of Object.keys(mods)) {
      const fk = normalizeBugSandboxFieldKey(rawKey, rawKey)
      if (fk && BUG_SANDBOX_DETAIL_FIELDS.includes(fk)) keys.add(fk)
    }
  }
  return keys
}

function bugSandboxFieldLabel(field) {
  if (field === 'expected_result') return '期望结果'
  if (field === 'actual_result') return '实际结果'
  if (field === 'steps_to_reproduce') return '复现步骤'
  return field
}

/**
 * Bug/Card 沙箱：只展示本次预览里出现的字段（后端 diff + modifications）。
 * 仅对已有行补全 delete 为空时的旧值；不再扫描 before/after 把未改动的详情字段画进沙箱。
 */
export function enrichBugSandboxDiffRows(nav, baseRows) {
  const tgt = String(nav?.target || '')
    .trim()
    .toLowerCase()
  if (tgt !== 'bug' && tgt !== 'card') {
    return Array.isArray(baseRows) ? baseRows : []
  }
  const rows = Array.isArray(baseRows) ? baseRows.map((r) => ({ ...r, lines: [...(r.lines || [])] })) : []
  const before = nav?.before
  const after = nav?.after
  const mods = nav?.modifications

  const upsert = (field, bo, ao) => {
    const oldD = formatBugSandboxFieldDisplay(field, bo)
    const newD = formatBugSandboxFieldDisplay(field, ao)
    if (!oldD && !newD) return false
    if (bugSandboxFieldValuesEqual(field, bo, ao)) return false
    const idx = rows.findIndex((r) => normalizeBugSandboxFieldKey(r?.field, r?.field_label) === field)
    const entry = {
      field,
      field_label: bugSandboxFieldLabel(field),
      lines: [
        { type: 'delete', content: oldD, line_no: 0 },
        { type: 'add', content: newD, line_no: 0 }
      ]
    }
    if (idx >= 0) rows[idx] = entry
    else rows.push(entry)
    return true
  }

  const previewFields = collectBugSandboxPreviewFieldKeys(rows, mods)

  for (const field of previewFields) {
    const bo =
      readBugModSide(mods, field, 'old') ??
      readBugSandboxFieldRaw(before, field)
    const ao =
      readBugModSide(mods, field, 'new') ??
      readBugSandboxFieldRaw(after, field)
    if (bo === undefined && ao === undefined) continue
    upsert(field, bo, ao)
  }

  return rows.filter((r) => {
    const fk = normalizeBugSandboxFieldKey(r?.field, r?.field_label)
    if (!fk || !BUG_SANDBOX_DETAIL_FIELDS.includes(fk)) return true
    const bo =
      readBugModSide(mods, fk, 'old') ??
      readBugSandboxFieldRaw(before, fk)
    const ao =
      readBugModSide(mods, fk, 'new') ??
      readBugSandboxFieldRaw(after, fk)
    if (bo === undefined && ao === undefined) {
      const del = r?.lines?.find((l) => l.type === 'delete')?.content
      const add = r?.lines?.find((l) => l.type === 'add')?.content
      return (
        (del != null && String(del).trim() !== '') ||
        (add != null && String(add).trim() !== '') ||
        r?.lines?.some((l) => l.type === 'unchanged')
      )
    }
    return !bugSandboxFieldValuesEqual(fk, bo, ao)
  })
}

export function resolveBugExpectedResultOldDisplay(modEntry, loadedFormValue, beforeRow) {
  const fromMod = modEntry?.old
  if (fromMod != null && String(fromMod).trim() !== '') {
    return formatBugExpectedResultForDisplay(fromMod)
  }
  const fromForm = loadedFormValue != null ? String(loadedFormValue).trim() : ''
  if (fromForm) return formatBugExpectedResultForDisplay(fromForm)
  const fromBefore = readBugExpectedResultFromRow(beforeRow)
  if (fromBefore) return formatBugExpectedResultForDisplay(fromBefore)
  return ''
}

/** pendingDiff.modifications 中解析复现步骤 {old,new} 的实际 key */
export function resolveBugReproModifyStoreKey(mods, requested = 'reproduction_steps') {
  if (!mods || typeof mods !== 'object') return null
  const tryKeys = [
    requested,
    'steps_to_reproduce',
    'reproduction_steps',
    'reproduce_steps'
  ].filter(Boolean)
  for (const k of tryKeys) {
    if (mods[k] && typeof mods[k] === 'object' && ('old' in mods[k] || 'new' in mods[k])) {
      return k
    }
  }
  return null
}

/** 展示用旧值：diff.old 为空时回退到已加载的 Bug 表单或 before 快照 */
export function resolveBugReproStepsOldDisplay(modEntry, loadedFormSteps, beforeRow) {
  const fromMod = modEntry?.old
  if (fromMod != null && String(fromMod).trim() !== '') {
    return formatBugReproductionStepsForDisplay(fromMod)
  }
  const fromForm = loadedFormSteps != null ? String(loadedFormSteps).trim() : ''
  if (fromForm) return formatBugReproductionStepsForDisplay(fromForm)
  const fromBefore = readBugReproductionStepsFromRow(beforeRow)
  if (fromBefore) return formatBugReproductionStepsForDisplay(fromBefore)
  return ''
}
