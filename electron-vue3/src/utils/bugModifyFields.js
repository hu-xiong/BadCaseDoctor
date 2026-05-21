/**
 * Bug modify / 沙箱 / 详情 diff：复现步骤等字段与后端 steps_to_reproduce 对齐。
 */
import { stripHtmlForModifyDisplay } from './testcaseModifyFields.js'

export const BUG_REPRODUCTION_STEP_KEYS = [
  'steps_to_reproduce',
  'reproduction_steps',
  'reproduce_steps',
  'description'
]

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

/** pendingDiff.modifications 中解析复现步骤 {old,new} 的实际 key */
export function resolveBugReproModifyStoreKey(mods, requested = 'reproduction_steps') {
  if (!mods || typeof mods !== 'object') return null
  const tryKeys = [
    requested,
    'steps_to_reproduce',
    'reproduction_steps',
    'reproduce_steps',
    'description'
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
