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

/** 属性区下拉框：与 Bug 优先级一致，行内 diff + 灌入 new 到 select */
export const TESTCASE_SELECT_DETAIL_FIELDS = ['case_type', 'priority', 'test_type']

/** 长文本详情字段：仅 Monaco / 富文本 diff，不预填控件 */
export const TESTCASE_MONACO_DETAIL_FIELDS = TESTCASE_DETAIL_FIELDS.filter(
  (f) => !TESTCASE_SELECT_DETAIL_FIELDS.includes(f)
)

/** 详情富文本/步骤等不把 new 预填进控件；下拉属性会预填（对齐 NewBug） */
export const TESTCASE_DETAIL_NO_PREFILL = new Set(TESTCASE_MONACO_DETAIL_FIELDS)

export const TESTCASE_CASE_TYPE_OPTIONS = ['功能测试', '接口测试', '性能测试', '安全测试']
export const TESTCASE_TEST_TYPE_OPTIONS = ['手动', '自动', '探索']
export const TESTCASE_PRIORITY_OPTIONS = ['P0', 'P1', 'P2', 'P3']

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

/** 模型/后端常见误写字段 → 详情表单列名 */
const TESTCASE_FIELD_KEY_ALIASES = {
  testcase_type: 'case_type',
  test_case_type: 'case_type',
  testcase_case_type: 'case_type',
  case_type_test: 'case_type',
  testcase_test_type: 'test_type',
  test_case_test_type: 'test_type',
  important_level: 'priority',
  importance: 'priority',
  precondition: 'preconditions',
  pre_conditions: 'preconditions',
  test_step: 'steps',
  test_steps: 'steps'
}

export const TESTCASE_ROW_ALIASES = {
  preconditions: ['preconditions', 'precondition'],
  steps: ['steps', 'test_steps'],
  remark: ['remark'],
  baseline: ['baseline'],
  case_type: ['case_type', 'caseType', 'testcase_type', 'test_case_type'],
  test_type: ['test_type', 'testType', 'testcase_test_type'],
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
  if (TESTCASE_FIELD_KEY_ALIASES[f]) return TESTCASE_FIELD_KEY_ALIASES[f]
  if (lab && LABEL_TO_KEY_ZH[lab]) return LABEL_TO_KEY_ZH[lab]
  if (f && TESTCASE_FIELD_LABEL_I18N[f]) return f
  return f || lab
}

/** 沙箱 diff 行：字段名归一 + i18n 标签（与详情 testcaseFieldLabel 一致） */
export function normalizeTestcaseSandboxDiffRow(row, t) {
  if (!row || typeof row !== 'object') return row
  const nk = normalizeTestcaseModifyFieldKey(row.field, row.field_label)
  const isTc =
    TESTCASE_DETAIL_FIELDS.includes(nk) ||
    TESTCASE_LIST_FIELDS.includes(nk) ||
    TESTCASE_FIELD_KEY_ALIASES[String(row.field || '').trim().toLowerCase().replace(/-/g, '_')]
  if (!isTc) return row
  return {
    ...row,
    field: nk,
    field_label: getTestcaseFieldLabel(t, nk, row.field_label)
  }
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

/** 单条步骤 → 详情编辑器 { step, expected } */
export function normalizeTestcaseStepItem(st) {
  if (st == null || typeof st !== 'object') {
    return { step: st != null ? String(st).trim() : '', expected: '' }
  }
  return {
    step: String(
      st.step ?? st.step_desc ?? st.content ?? st.description ?? ''
    ).trim(),
    expected: String(st.expected ?? st.expected_result ?? '').trim()
  }
}

/** 从 JSON 字符串 / 数组 / 展示文案解析步骤列表；失败返回 null */
export function parseTestcaseStepsInput(raw) {
  if (raw == null) return null
  if (Array.isArray(raw)) {
    return raw.map((st) => normalizeTestcaseStepItem(st))
  }
  if (typeof raw === 'object') {
    return [normalizeTestcaseStepItem(raw)]
  }
  const t = String(raw).trim()
  if (!t) return null
  if (t.startsWith('[')) {
    try {
      const parsed = JSON.parse(t)
      if (Array.isArray(parsed)) return parsed.map((st) => normalizeTestcaseStepItem(st))
    } catch (_e) {
      /* fall through */
    }
  }
  const lines = t.split('\n').map((l) => l.trim()).filter(Boolean)
  if (lines.length === 0) return null
  const fromDisplay = []
  for (const line of lines) {
    const m = line.match(/^\d+\.\s*(.*?)(?:\s*→\s*(.*))?$/)
    if (m) {
      fromDisplay.push({
        step: (m[1] || '').trim(),
        expected: (m[2] || '').trim()
      })
    }
  }
  if (fromDisplay.length > 0) return fromDisplay
  return null
}

/** 详情表单 steps：至少保留一行空步骤 */
export function normalizeTestcaseStepsForEditor(raw) {
  const parsed = parseTestcaseStepsInput(raw)
  if (parsed && parsed.length > 0) return parsed
  return [{ step: '', expected: '' }]
}

/** 比较详情字段是否实质相同（优先级兼容 P3/p3） */
export function testcaseDetailFieldValuesEqual(fieldKey, a, b) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  if (nk === 'priority') {
    return formatTestcasePriorityForDisplay(a) === formatTestcasePriorityForDisplay(b)
  }
  if (nk === 'steps') {
    const pa = normalizeTestcaseStepsForEditor(a)
    const pb = normalizeTestcaseStepsForEditor(b)
    return JSON.stringify(pa) === JSON.stringify(pb)
  }
  return String(a ?? '').trim() === String(b ?? '').trim()
}

/** diff 行 delete/add 是否展示为不同内容 */
export function testcaseSandboxDiffLinesShowChange(row) {
  if (!row || typeof row !== 'object') return false
  const oldL = row.lines?.find((l) => l.type === 'delete')
  const newL = row.lines?.find((l) => l.type === 'add')
  const o = oldL?.content != null ? String(oldL.content).trim() : ''
  const n = newL?.content != null ? String(newL.content).trim() : ''
  return o !== n && Boolean(o || n)
}

/** 从 modifications 读取新值（扁平或 { old, new }） */
export function readTestcaseModifyNewValue(mods, fieldKey) {
  if (!mods || typeof mods !== 'object') return undefined
  for (const mk of getTestcaseModifyModKeys(fieldKey)) {
    const m = mods[mk]
    if (m == null) continue
    if (typeof m === 'object' && m !== null && 'new' in m) return m.new
    return m
  }
  return undefined
}

/** after 快照优先；缺失时用 modifications 中的新值 */
export function readTestcaseEffectiveAfter(nav, fieldKey) {
  const fromAfter = readTestcaseDetailRawField(nav?.after, fieldKey)
  if (fromAfter !== undefined) return fromAfter
  return readTestcaseModifyNewValue(nav?.modifications, fieldKey)
}

/** 采纳 / 落库用：读 before|after 快照中的原始值（非展示文案） */
export function readTestcaseDetailRawField(row, fieldKey) {
  if (!row || typeof row !== 'object') return undefined
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  const keys = TESTCASE_ROW_ALIASES[nk] || [nk]
  for (const k of keys) {
    if (!Object.prototype.hasOwnProperty.call(row, k)) continue
    const v = row[k]
    if (v == null) continue
    if (Array.isArray(v) && v.length === 0) continue
    if (typeof v === 'string' && v.trim() === '') continue
    return v
  }
  return undefined
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
      const parsed = parseTestcaseStepsInput(t)
      if (parsed && parsed.length > 0) {
        arr = parsed
      } else {
        return t
      }
    }
  }
  if (!Array.isArray(arr)) return String(raw).trim()
  if (arr.length === 0) return ''
  return arr
    .map((st, i) => {
      const step = st?.step ?? st?.step_desc ?? st?.content ?? st?.description ?? ''
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
  const u = String(raw).trim().toUpperCase()
  if (TESTCASE_PRIORITY_OPTIONS.includes(u)) return u
  return String(raw).trim()
}

/** 详情 select v-model：归一优先级（p3 / P3 / P3 - 中 → P3） */
export function normalizeTestcasePriorityForSelect(raw) {
  const disp = formatTestcasePriorityForDisplay(raw)
  if (disp && TESTCASE_PRIORITY_OPTIONS.includes(disp.toUpperCase())) {
    return disp.toUpperCase()
  }
  return 'P3'
}

export function normalizeTestcaseCaseTypeForSelect(raw) {
  const s = String(raw ?? '').trim()
  if (TESTCASE_CASE_TYPE_OPTIONS.includes(s)) return s
  for (const o of TESTCASE_CASE_TYPE_OPTIONS) {
    if (s.includes(o)) return o
  }
  return s || TESTCASE_CASE_TYPE_OPTIONS[0]
}

export function normalizeTestcaseTestTypeForSelect(raw) {
  const s = String(raw ?? '').trim()
  if (TESTCASE_TEST_TYPE_OPTIONS.includes(s)) return s
  for (const o of TESTCASE_TEST_TYPE_OPTIONS) {
    if (s.includes(o)) return o
  }
  return s || TESTCASE_TEST_TYPE_OPTIONS[0]
}

/**
 * 下拉属性展示文案（详情 diff 面板 + 沙箱，对齐 Bug formatBugPriorityLabel）
 * @param {string} fieldKey
 * @param {*} raw
 * @param {function} [t] - vue-i18n t，用于「未设置」
 */
export function formatTestcaseSelectFieldLabel(fieldKey, raw, t) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  const notSet =
    typeof t === 'function'
      ? (() => {
          const tr = t('chat.notSet')
          return tr && tr !== 'chat.notSet' ? tr : '未设置'
        })()
      : '未设置'
  if (raw == null || String(raw).trim() === '') return notSet
  if (nk === 'priority') {
    const p = normalizeTestcasePriorityForSelect(raw)
    return p || notSet
  }
  if (nk === 'case_type') {
    const v = normalizeTestcaseCaseTypeForSelect(raw)
    return v || notSet
  }
  if (nk === 'test_type') {
    const v = normalizeTestcaseTestTypeForSelect(raw)
    return v || notSet
  }
  return String(raw).trim() || notSet
}

export function normalizeTestcaseSelectFieldForEditor(fieldKey, raw) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  if (nk === 'priority') return normalizeTestcasePriorityForSelect(raw)
  if (nk === 'case_type') return normalizeTestcaseCaseTypeForSelect(raw)
  if (nk === 'test_type') return normalizeTestcaseTestTypeForSelect(raw)
  return raw
}

export function isTestcaseSelectDetailField(fieldKey) {
  return TESTCASE_SELECT_DETAIL_FIELDS.includes(normalizeTestcaseModifyFieldKey(fieldKey))
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
  } else if (isTestcaseSelectDetailField(nk)) {
    s = formatTestcaseSelectFieldLabel(nk, raw)
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
 * 测例沙箱/详情：合并 diff 行、before/after、modifications，输出可展示行。
 * @param {object} nav - { target, before, after, modifications }
 * @param {Array} baseRows - 后端 diff 行（可先 normalizeTestcaseSandboxDiffRow）
 * @param {function} t - vue-i18n t
 */
export function enrichTestcaseSandboxDiffRows(nav, baseRows, t) {
  const tgt = String(nav?.target || '')
    .trim()
    .toLowerCase()
  if (tgt !== 'testcase' && tgt !== 'test_case') {
    return Array.isArray(baseRows) ? baseRows : []
  }
  const rows = Array.isArray(baseRows) ? baseRows.map((r) => normalizeTestcaseSandboxDiffRow(r, t)) : []
  const before = nav?.before
  const after = nav?.after
  const mods = nav?.modifications
  const seen = new Set(rows.map((r) => normalizeTestcaseModifyFieldKey(r?.field, r?.field_label)))

  const formatSide = (fk, val) =>
    isTestcaseSelectDetailField(fk)
      ? formatTestcaseSelectFieldLabel(fk, val, t)
      : formatTestcaseModifyFieldValue(fk, val)

  const upsertRow = (fk, bo, ao) => {
    if (testcaseDetailFieldValuesEqual(fk, bo, ao) && !formatSide(fk, ao)) {
      return
    }
    const oldD = formatSide(fk, bo)
    const newD = formatSide(fk, ao)
    const existingIdx = rows.findIndex(
      (r) => normalizeTestcaseModifyFieldKey(r?.field, r?.field_label) === fk
    )
    const entry = {
      field: fk,
      field_label: getTestcaseFieldLabel(t, fk),
      lines: [
        { type: 'delete', content: oldD, line_no: 0 },
        { type: 'add', content: newD, line_no: 0 }
      ]
    }
    if (existingIdx >= 0) rows[existingIdx] = entry
    else rows.push(entry)
    seen.add(fk)
  }

  for (let i = rows.length - 1; i >= 0; i--) {
    const fk = normalizeTestcaseModifyFieldKey(rows[i]?.field, rows[i]?.field_label)
    if (testcaseSandboxDiffLinesShowChange(rows[i])) continue
    const bo = readTestcaseDetailRawField(before, fk)
    const ao = readTestcaseEffectiveAfter(nav, fk)
    if (testcaseDetailFieldValuesEqual(fk, bo, ao)) {
      rows.splice(i, 1)
      seen.delete(fk)
    }
  }

  const allDetailFields = [
    ...TESTCASE_DETAIL_FIELDS,
    ...TESTCASE_LIST_FIELDS.filter((f) => f !== 'title' && f !== 'status' && f !== 'assignee')
  ]
  const fieldsToScan = [...new Set([...allDetailFields, ...seen])]

  for (const fk of fieldsToScan) {
    if (!TESTCASE_DETAIL_FIELDS.includes(fk) && !['case_type', 'priority', 'test_type'].includes(fk)) {
      continue
    }
    const bo = readTestcaseDetailRawField(before, fk)
    const ao = readTestcaseEffectiveAfter(nav, fk)
    if (ao === undefined && bo === undefined) continue
    if (seen.has(fk) && !testcaseSandboxDiffLinesShowChange(rows.find(
      (r) => normalizeTestcaseModifyFieldKey(r?.field, r?.field_label) === fk
    ))) {
      const row = rows.find((r) => normalizeTestcaseModifyFieldKey(r?.field, r?.field_label) === fk)
      if (row && testcaseSandboxDiffLinesShowChange(row)) continue
      if (testcaseDetailFieldValuesEqual(fk, bo, ao)) continue
    }
    if (testcaseDetailFieldValuesEqual(fk, bo, ao)) continue
    upsertRow(fk, bo, ao)
  }

  if (mods && typeof mods === 'object') {
    for (const rawKey of Object.keys(mods)) {
      const fk = normalizeTestcaseModifyFieldKey(rawKey)
      if (!TESTCASE_DETAIL_FIELDS.includes(fk)) continue
      if (seen.has(fk)) continue
      const bo = readTestcaseDetailRawField(before, fk)
      const ao = readTestcaseModifyNewValue(mods, fk)
      if (ao === undefined) continue
      if (testcaseDetailFieldValuesEqual(fk, bo, ao)) continue
      upsertRow(fk, bo, ao)
    }
  }

  return rows
}

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
