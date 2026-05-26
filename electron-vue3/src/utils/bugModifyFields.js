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

/** Bug/Card 沙箱：补全 diff delete 为空时的旧值行（与测例 enrichTestcaseSandboxDiffRows 对齐） */
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
  const seen = new Set(
    rows.map((r) => String(r?.field || '').trim().toLowerCase())
  )

  const upsert = (field, bo, ao) => {
    const oldD = formatBugSandboxFieldDisplay(field, bo)
    const newD = formatBugSandboxFieldDisplay(field, ao)
    if (!oldD && !newD) return
    const idx = rows.findIndex((r) => String(r?.field || '').trim().toLowerCase() === field)
    const entry = {
      field,
      field_label: field === 'expected_result' ? '期望结果' : field === 'actual_result' ? '实际结果' : '复现步骤',
      lines: [
        { type: 'delete', content: oldD, line_no: 0 },
        { type: 'add', content: newD, line_no: 0 }
      ]
    }
    if (idx >= 0) rows[idx] = entry
    else rows.push(entry)
    seen.add(field)
  }

  for (const field of BUG_SANDBOX_DETAIL_FIELDS) {
    const bo =
      readBugModSide(mods, field, 'old') ??
      readBugSandboxFieldRaw(before, field)
    const ao =
      readBugModSide(mods, field, 'new') ??
      readBugSandboxFieldRaw(after, field)
    if (bo === undefined && ao === undefined) continue
    const existing = rows.find((r) => String(r?.field || '').trim().toLowerCase() === field)
    const del = existing?.lines?.find((l) => l.type === 'delete')?.content
    if (existing && del != null && String(del).trim() !== '') continue
    if (bugSandboxFieldValuesEqual(field, bo, ao) && !formatBugSandboxFieldDisplay(field, ao)) continue
    upsert(field, bo, ao)
  }

  return rows
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
