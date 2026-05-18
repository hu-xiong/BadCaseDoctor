/**
 * 测试用例 modify / 沙箱 / 详情 diff 共用：字段归一、展示文案、快照读取。
 * 列表字段仅 title/status/assignee；其余在详情页与沙箱中展示。
 */

export const TESTCASE_LIST_FIELDS = ['title', 'status', 'assignee']

export const TESTCASE_DETAIL_FIELDS = [
  'preconditions',
  'steps',
  'remark',
  'baseline',
  'priority',
  'case_type',
  'test_type'
]

/** 详情编辑器不把 new 预填进控件，由 field-diff / Monaco 展示变更 */
export const TESTCASE_DETAIL_NO_PREFILL = new Set(TESTCASE_DETAIL_FIELDS)

/** i18n key（cardDetail.*） */
export const TESTCASE_FIELD_LABEL_I18N = {
  title: 'cardDetail.title',
  status: 'cardDetail.status',
  assignee: 'cardDetail.assignee',
  priority: 'cardDetail.priority',
  preconditions: 'cardDetail.preconditions',
  steps: 'cardDetail.steps',
  remark: 'cardDetail.remark',
  baseline: 'cardDetail.baseline',
  case_type: 'cardDetail.caseType',
  test_type: 'cardDetail.testType'
}

const LABEL_TO_KEY_ZH = {
  前置条件: 'preconditions',
  用例步骤: 'steps',
  测试步骤: 'steps',
  步骤: 'steps',
  备注: 'remark',
  基线: 'baseline',
  用例类型: 'case_type',
  测试类型: 'test_type',
  重要程度: 'priority',
  优先级: 'priority',
  标题: 'title',
  状态: 'status',
  负责人: 'assignee'
}

export const TESTCASE_ROW_ALIASES = {
  preconditions: ['preconditions', 'precondition'],
  steps: ['steps', 'test_steps'],
  remark: ['remark'],
  baseline: ['baseline'],
  case_type: ['case_type', 'caseType'],
  test_type: ['test_type', 'testType'],
  priority: ['priority'],
  assignee: ['assignee_display', 'assignee', 'assignee_id']
}

export function normalizeTestcaseModifyFieldKey(fk, label = '') {
  const f = String(fk || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_')
  const lab = String(label || '').trim()
  if (f === 'precondition' || lab === 'precondition') return 'preconditions'
  if (lab && LABEL_TO_KEY_ZH[lab]) return LABEL_TO_KEY_ZH[lab]
  if (f && TESTCASE_FIELD_LABEL_I18N[f]) return f
  return f || lab
}

export function isTestcaseDetailModifyField(fieldKey, label = '') {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey, label)
  return TESTCASE_DETAIL_FIELDS.includes(nk)
}

export function isTestcaseListModifyField(fieldKey, label = '') {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey, label)
  return TESTCASE_LIST_FIELDS.includes(nk)
}

export function getTestcaseModifyModKeys(fieldKey, rawField) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey, rawField)
  const keys = new Set([nk, rawField, fieldKey].filter(Boolean).map(String))
  const aliases = TESTCASE_ROW_ALIASES[nk]
  if (aliases) aliases.forEach((k) => keys.add(k))
  return [...keys]
}

export function getTestcaseFieldLabel(t, fieldKey, label = '') {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey, label)
  const i18nKey = TESTCASE_FIELD_LABEL_I18N[nk]
  if (i18nKey && typeof t === 'function') {
    const tr = t(i18nKey)
    if (tr && tr !== i18nKey) return tr
  }
  if (label && /[\u4e00-\u9fff]/.test(label)) return label
  return nk || String(fieldKey || '')
}

export function stripHtmlForModifyDisplay(raw) {
  if (raw == null) return ''
  const s = String(raw)
  if (!s.trim()) return ''
  if (!/<[a-z][\s\S]*>/i.test(s)) return s.trim()
  return s
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+\n/g, '\n')
    .trim()
}

export function formatTestcaseStepsForDisplay(raw) {
  if (raw == null) return ''
  let arr = raw
  if (typeof raw === 'string') {
    const t = raw.trim()
    if (!t) return ''
    if (t.startsWith('[')) {
      try {
        arr = JSON.parse(t)
      } catch (_e) {
        return t
      }
    } else {
      return t
    }
  }
  if (!Array.isArray(arr)) return String(raw).trim()
  if (arr.length === 0) return ''
  return arr
    .map((st, i) => {
      const step = st?.step ?? st?.content ?? st?.description ?? ''
      const exp = st?.expected ?? st?.expected_result ?? ''
      return `${i + 1}. ${step}${exp ? ` → ${exp}` : ''}`
    })
    .join('\n')
}

const PRIORITY_DISPLAY = {
  p0: 'P0',
  p1: 'P1',
  p2: 'P2',
  p3: 'P3',
  p4: 'P4'
}

export function formatTestcasePriorityForDisplay(raw) {
  if (raw == null || String(raw).trim() === '') return ''
  const s = String(raw).trim().toLowerCase()
  if (PRIORITY_DISPLAY[s]) return PRIORITY_DISPLAY[s]
  return String(raw).trim()
}

/**
 * @param {string} fieldKey
 * @param {*} raw
 * @param {{ maxLen?: number }} opts
 */
export function formatTestcaseModifyFieldValue(fieldKey, raw, opts = {}) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  const maxLen = opts.maxLen ?? 480
  let s = ''
  if (nk === 'steps') {
    s = formatTestcaseStepsForDisplay(raw)
  } else if (nk === 'priority') {
    s = formatTestcasePriorityForDisplay(raw)
  } else if (nk === 'preconditions' || nk === 'remark') {
    s = stripHtmlForModifyDisplay(raw)
  } else if (raw != null && typeof raw === 'object') {
    try {
      s = JSON.stringify(raw)
    } catch (_e) {
      s = String(raw)
    }
  } else {
    s = raw != null ? String(raw).trim() : ''
  }
  if (s.length > maxLen) return `${s.slice(0, maxLen)}…`
  return s
}

export function readTestcaseRowField(row, fieldKey) {
  if (!row || typeof row !== 'object') return ''
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  const keys = TESTCASE_ROW_ALIASES[nk] || [nk]
  for (const k of keys) {
    if (!Object.prototype.hasOwnProperty.call(row, k)) continue
    const v = row[k]
    if (v == null) continue
    if (Array.isArray(v) && v.length === 0) continue
    if (typeof v === 'string' && v.trim() === '') continue
    return formatTestcaseModifyFieldValue(nk, v, { maxLen: 2000 })
  }
  return ''
}

/**
 * 从 before/after / modifications 解析沙箱或详情 diff 一侧的展示值。
 * 优先用后端下发的 before/after 快照（modified_data 已 merge modifications）；
 * modifications 可能是扁平 { field: newVal } 或 { field: { old, new } }。
 */
export function readTestcaseModifySideValue(ctx, fieldKey, rawField, fieldLabel, which, mods = {}) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey, fieldLabel)
  const fromBefore = readTestcaseRowField(ctx?.before, nk)
  const fromAfter = readTestcaseRowField(ctx?.after, nk)

  if (which === 'old' && fromBefore) return fromBefore
  if (which === 'new' && fromAfter) return fromAfter

  const modKeys = getTestcaseModifyModKeys(nk, rawField)
  for (const mk of modKeys) {
    const m = mods[mk]
    if (m == null) continue
    if (typeof m === 'object' && ('old' in m || 'new' in m)) {
      const v = which === 'old' ? m.old : m.new
      const formatted = formatTestcaseModifyFieldValue(nk, v)
      if (formatted) return formatted
    } else if (which === 'new') {
      const formatted = formatTestcaseModifyFieldValue(nk, m)
      if (formatted) return formatted
    }
  }

  return which === 'old' ? fromBefore : fromAfter
}
