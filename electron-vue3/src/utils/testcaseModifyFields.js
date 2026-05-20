/**
 * 测试用例 modify / 沙箱 / 详情 diff 共用：字段归一、展示文案、快照读取。
 * 列表字段仅 title/status/assignee；其余在详情页与沙箱中展示。
 */

export const TESTCASE_LIST_FIELDS = ['title', 'status', 'assignee']

export const TESTCASE_DETAIL_FIELDS = [
  'preconditions',
  'steps',
  'priority',
  'case_type',
  'test_type',
  'execution_result',
  'related_defects',
  'append_comment'
]

/** 属性区下拉框：与 Bug 优先级一致，行内 diff + 灌入 new 到 select */
export const TESTCASE_SELECT_DETAIL_FIELDS = ['case_type', 'priority', 'test_type', 'execution_result']

/** 长文本详情字段：仅 Monaco / 富文本 diff，不预填控件 */
export const TESTCASE_MONACO_DETAIL_FIELDS = TESTCASE_DETAIL_FIELDS.filter(
  (f) => !TESTCASE_SELECT_DETAIL_FIELDS.includes(f)
)

/** 详情富文本/步骤等不把 new 预填进控件；下拉属性会预填（对齐 NewBug） */
export const TESTCASE_DETAIL_NO_PREFILL = new Set(TESTCASE_MONACO_DETAIL_FIELDS)

export const TESTCASE_CASE_TYPE_OPTIONS = ['功能测试', '接口测试', '性能测试', '安全测试']
export const TESTCASE_TEST_TYPE_OPTIONS = ['手动', '自动', '探索']
export const TESTCASE_PRIORITY_OPTIONS = ['P0', 'P1', 'P2', 'P3']
/** v-model 值；空字符串表示未执行（与后端 NULL 对齐） */
export const TESTCASE_EXECUTION_RESULT_OPTIONS = ['', 'pass', 'fail', 'blocked', 'skip']

const EXECUTION_RESULT_LABEL_ZH = {
  '': '未执行',
  pass: '通过',
  fail: '失败',
  blocked: '阻塞',
  skip: '跳过'
}

const EXECUTION_RESULT_FROM_TEXT = {
  未执行: '',
  通过: 'pass',
  失败: 'fail',
  阻塞: 'blocked',
  跳过: 'skip',
  pass: 'pass',
  fail: 'fail',
  blocked: 'blocked',
  skip: 'skip',
  passed: 'pass',
  failed: 'fail'
}

/** i18n key（cardDetail.*） */
export const TESTCASE_FIELD_LABEL_I18N = {
  title: 'cardDetail.title',
  status: 'cardDetail.status',
  assignee: 'cardDetail.assignee',
  priority: 'cardDetail.priority',
  preconditions: 'cardDetail.preconditions',
  steps: 'cardDetail.steps',
  case_type: 'cardDetail.caseType',
  test_type: 'cardDetail.testType',
  execution_result: 'cardDetail.executionResult',
  related_defects: 'cardDetail.relatedDefects',
  append_comment: 'testcaseComment.appendTitle'
}

const LABEL_TO_KEY_ZH = {
  前置条件: 'preconditions',
  用例步骤: 'steps',
  测试步骤: 'steps',
  步骤: 'steps',
  用例类型: 'case_type',
  测试类型: 'test_type',
  重要程度: 'priority',
  优先级: 'priority',
  执行结果: 'execution_result',
  result: 'execution_result',
  关联缺陷: 'related_defects',
  关联bug: 'related_defects',
  关联Bug: 'related_defects',
  评论: 'append_comment',
  追加评论: 'append_comment',
  添加评论: 'append_comment',
  备注: 'append_comment',
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
  test_steps: 'steps',
  test_result: 'execution_result',
  execution: 'execution_result',
  result: 'execution_result',
  related_defect: 'related_defects',
  related_defects: 'related_defects',
  defects: 'related_defects',
  comment: 'append_comment',
  append_comment: 'append_comment',
  remark: 'append_comment'
}

export const TESTCASE_ROW_ALIASES = {
  preconditions: ['preconditions', 'precondition'],
  steps: ['steps', 'test_steps'],
  case_type: ['case_type', 'caseType', 'testcase_type', 'test_case_type'],
  test_type: ['test_type', 'testType', 'testcase_test_type'],
  priority: ['priority'],
  execution_result: ['execution_result', 'executionResult', 'test_result', 'testResult'],
  related_defects: ['related_defects', 'relatedDefects', 'defects', 'related_bugs'],
  assignee: ['assignee_display', 'assignee', 'assignee_id']
}

/** 归一为 Bug 主键字符串数组（全量替换语义） */
export function normalizeTestcaseRelatedDefectIds(raw) {
  if (raw == null) return []
  if (Array.isArray(raw)) {
    const out = []
    for (const item of raw) {
      if (item == null) continue
      let id = ''
      if (typeof item === 'object') {
        id = String(item.id ?? item.bug_id ?? item.bugId ?? '').trim()
      } else {
        id = String(item).trim()
      }
      if (!id) continue
      const m = id.match(/(\d{10,})/)
      if (m) id = m[1]
      if (!out.includes(id)) out.push(id)
    }
    return out
  }
  if (typeof raw === 'string') {
    const t = raw.trim()
    if (!t) return []
    if (t.startsWith('[')) {
      try {
        return normalizeTestcaseRelatedDefectIds(JSON.parse(t))
      } catch (_e) {
        /* fall through */
      }
    }
    const lines = t.split('\n').map((l) => l.trim()).filter(Boolean)
    const fromLines = []
    for (const line of lines) {
      const m = line.match(/Bug-?(\d{10,})/i) || line.match(/(\d{10,})/)
      if (m) fromLines.push(m[1])
    }
    if (fromLines.length) return [...new Set(fromLines)]
    return t
      .split(/[,;，；\s]+/)
      .map((s) => {
        const x = s.trim()
        if (!x) return ''
        const m = x.match(/(\d{10,})/)
        return m ? m[1] : x
      })
      .filter(Boolean)
  }
  return []
}

/** 从沙箱/修改导航快照提取 bugId → 标题（非占位） */
export function buildTestcaseRelatedDefectTitleMap(nav = {}) {
  const map = {}
  const ingestList = (raw) => {
    if (!Array.isArray(raw)) return
    for (const item of raw) {
      if (!item || typeof item !== 'object') continue
      let id = String(item.bug_id ?? item.bugId ?? item.id ?? '').trim()
      const m = id.match(/(\d{10,})/)
      if (m) id = m[1]
      if (!id) continue
      const title = String(item.title ?? item.name ?? '').trim()
      if (title && !isPlaceholderTestcaseDefectTitle(id, title)) map[id] = title
    }
  }
  const b = nav?.before
  const a = nav?.after
  if (b && typeof b === 'object') ingestList(b.related_defects ?? b.relatedDefects)
  if (a && typeof a === 'object') ingestList(a.related_defects ?? a.relatedDefects)
  const mods = nav?.modifications
  if (mods && typeof mods === 'object') {
    const rd = mods.related_defects ?? mods.relatedDefects
    if (rd && typeof rd === 'object' && !Array.isArray(rd) && ('old' in rd || 'new' in rd)) {
      ingestList(rd.old)
      ingestList(rd.new)
    } else {
      ingestList(rd)
    }
  }
  return map
}

/** 收集导航中涉及的关联缺陷 id（含 diff 行文案） */
export function collectTestcaseRelatedDefectIdsFromNav(nav = {}) {
  const out = []
  const push = (raw) => {
    for (const id of normalizeTestcaseRelatedDefectIds(raw)) {
      if (!out.includes(id)) out.push(id)
    }
  }
  if (!nav || typeof nav !== 'object') return out
  const b = nav.before
  const a = nav.after
  if (b && typeof b === 'object') push(b.related_defects ?? b.relatedDefects)
  if (a && typeof a === 'object') push(a.related_defects ?? a.relatedDefects)
  const mods = nav.modifications
  if (mods && typeof mods === 'object') {
    const rd = mods.related_defects ?? mods.relatedDefects
    if (rd && typeof rd === 'object' && !Array.isArray(rd) && ('old' in rd || 'new' in rd)) {
      push(rd.old)
      push(rd.new)
    } else {
      push(rd)
    }
  }
  if (Array.isArray(nav.diff)) {
    for (const row of nav.diff) {
      const fk = normalizeTestcaseModifyFieldKey(row?.field, row?.field_label)
      if (fk !== 'related_defects') continue
      for (const l of row.lines || []) {
        if (l?.content != null) push(l.content)
      }
    }
  }
  return out
}

export function testcaseRelatedDefectsEqual(a, b) {
  const aa = [...normalizeTestcaseRelatedDefectIds(a)].sort()
  const bb = [...normalizeTestcaseRelatedDefectIds(b)].sort()
  return JSON.stringify(aa) === JSON.stringify(bb)
}

const TESTCASE_COMMENT_INTENT_RE =
  /(?:添加|追加|发表|写|留|输入|新增).{0,10}?评论|评论.{0,10}?(?:一下|内容|为|：|:)|(?:append|add)\s*comment/i
const TESTCASE_REMARK_INTENT_RE =
  /(?:修改|更新|改|设置|填写|替换).{0,10}?备注|备注.{0,10}?(?:为|成|改成|改为|更新)/i

/** 自然语言是否表达「追加评论」而非改备注 */
export function intentRequestsTestcaseComment(intentText) {
  const t = String(intentText || '').trim()
  if (!t) return false
  const hasComment = TESTCASE_COMMENT_INTENT_RE.test(t)
  const hasRemark = TESTCASE_REMARK_INTENT_RE.test(t)
  if (hasRemark && !hasComment) return false
  return hasComment
}

/**
 * 纠正 Agent 误将评论写入 remark：remark → append_comment（保留 {old,new} 结构中的 new）
 * @returns {boolean} 是否发生了纠正
 */
export function coerceTestcaseRemarkToAppendComment(mods, intentText) {
  if (!mods || typeof mods !== 'object') return false
  if (mods.append_comment != null || mods.comment != null) return false
  if (mods.remark == null) return false
  if (!intentRequestsTestcaseComment(intentText)) return false
  const raw = mods.remark
  let newVal = raw
  if (raw && typeof raw === 'object') {
    if ('new' in raw) newVal = raw.new
    else if (raw.old != null) newVal = raw.old
  }
  mods.append_comment =
    raw && typeof raw === 'object' && !Array.isArray(raw)
      ? { ...raw, new: newVal, old: '' }
      : { new: newVal, old: '' }
  delete mods.remark
  return true
}

/** 是否为占位标题（Bug-123 / 纯 id），需拉取真实 Bug 标题 */
export function isPlaceholderTestcaseDefectTitle(id, title) {
  const idStr = String(id ?? '').trim()
  const t = String(title ?? '').trim()
  if (!t) return true
  if (!idStr) return false
  if (t === idStr) return true
  if (t === `Bug-${idStr}` || t === `Bug ${idStr}`) return true
  const digits = t.replace(/\D/g, '')
  if (digits === idStr && /^Bug[-\s]?\d+$/i.test(t)) return true
  return false
}

export function formatTestcaseRelatedDefectsForDisplay(raw, opts = {}) {
  const ids = normalizeTestcaseRelatedDefectIds(raw)
  const t = opts.t
  const titleMap = opts.titleMap || opts.bugTitleMap || {}
  const none =
    typeof t === 'function'
      ? (() => {
          const tr = t('testcaseRelatedDefects.none')
          return tr && tr !== 'testcaseRelatedDefects.none' ? tr : '（无）'
        })()
      : '（无）'
  if (ids.length === 0) return none
  return ids
    .map((id) => {
      const title = titleMap[id] || titleMap[String(id)]
      if (title && !isPlaceholderTestcaseDefectTitle(id, title)) return title
      return `Bug-${id}`
    })
    .join('\n')
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
/** 是否为测例「执行结果」枚举值（pass/fail 等），与工作流 status 区分 */
export function isTestcaseExecutionResultEnumValue(raw) {
  const n = normalizeTestcaseExecutionResultForSelect(raw)
  return n === 'pass' || n === 'fail' || n === 'blocked' || n === 'skip'
}

/**
 * 沙箱 diff：模型常把执行结果写到 status，或 field_label 写「执行结果」但 field 为 status
 */
export function remapMislabeledTestcaseSandboxFieldKey(fieldKey, fieldLabel = '', sampleValue = null) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey, fieldLabel)
  const lab = String(fieldLabel || '').trim()
  if (nk === 'execution_result' || /执行结果|test\s*result/i.test(lab)) {
    return 'execution_result'
  }
  if (nk === 'status' && isTestcaseExecutionResultEnumValue(sampleValue)) {
    return 'execution_result'
  }
  return nk
}

/** 已有 execution_result 变更时，隐藏误标的 status 行（评审→pass） */
export function shouldSuppressMislabeledTestcaseStatusSandboxRow(row, nav) {
  const fk = normalizeTestcaseModifyFieldKey(row?.field, row?.field_label)
  if (fk !== 'status') return false
  const mods = nav?.modifications
  if (mods && typeof mods === 'object') {
    for (const k of Object.keys(mods)) {
      if (String(k).startsWith('_')) continue
      if (normalizeTestcaseModifyFieldKey(k) === 'execution_result') return true
    }
  }
  const newL = row?.lines?.find((l) => l.type === 'add')
  const oldL = row?.lines?.find((l) => l.type === 'delete')
  const sample = newL?.content ?? oldL?.content
  if (isTestcaseExecutionResultEnumValue(sample)) return true
  if (/执行结果|test\s*result/i.test(String(row?.field_label || ''))) return true
  return false
}

export function normalizeTestcaseExecutionResultForSelect(raw) {
  if (raw == null) return ''
  const s = String(raw).trim()
  if (!s) return ''
  if (Object.prototype.hasOwnProperty.call(EXECUTION_RESULT_FROM_TEXT, s)) {
    return EXECUTION_RESULT_FROM_TEXT[s]
  }
  const lower = s.toLowerCase()
  if (Object.prototype.hasOwnProperty.call(EXECUTION_RESULT_FROM_TEXT, lower)) {
    return EXECUTION_RESULT_FROM_TEXT[lower]
  }
  if (TESTCASE_EXECUTION_RESULT_OPTIONS.includes(lower)) return lower
  return ''
}

const EXECUTION_RESULT_I18N_KEYS = {
  '': 'testcaseExecution.notRun',
  pass: 'testcaseExecution.pass',
  fail: 'testcaseExecution.fail',
  blocked: 'testcaseExecution.blocked',
  skip: 'testcaseExecution.skip'
}

export function formatTestcaseExecutionResultLabel(raw, t) {
  const notSet =
    typeof t === 'function'
      ? (() => {
          const tr = t('chat.notSet')
          return tr && tr !== 'chat.notSet' ? tr : '未设置'
        })()
      : '未设置'
  const v = normalizeTestcaseExecutionResultForSelect(raw)
  if (v === '') {
    if (typeof t === 'function') {
      const tr = t(EXECUTION_RESULT_I18N_KEYS[''])
      if (tr && tr !== EXECUTION_RESULT_I18N_KEYS['']) return tr
    }
    return EXECUTION_RESULT_LABEL_ZH[''] || '未执行'
  }
  if (typeof t === 'function') {
    const key = EXECUTION_RESULT_I18N_KEYS[v]
    if (key) {
      const tr = t(key)
      if (tr && tr !== key) return tr
    }
  }
  const zh = EXECUTION_RESULT_LABEL_ZH[v]
  return zh || v || notSet
}

export function testcaseDetailFieldValuesEqual(fieldKey, a, b) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  if (nk === 'priority') {
    return formatTestcasePriorityForDisplay(a) === formatTestcasePriorityForDisplay(b)
  }
  if (nk === 'execution_result') {
    return (
      normalizeTestcaseExecutionResultForSelect(a) ===
      normalizeTestcaseExecutionResultForSelect(b)
    )
  }
  if (nk === 'related_defects') {
    return testcaseRelatedDefectsEqual(a, b)
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
    if (nk === 'execution_result') {
      if (v == null) return ''
      if (typeof v === 'string') return v
      return String(v)
    }
    if (nk === 'related_defects') {
      if (v == null) return []
      return normalizeTestcaseRelatedDefectIds(v)
    }
    if (v == null) continue
    if (Array.isArray(v) && v.length === 0) continue
    if (typeof v === 'string' && v.trim() === '') continue
    return v
  }
  return undefined
}

/** before 快照 + modifications.old（测例执行结果空串也视为有效旧值） */
export function readTestcaseEffectiveBefore(nav, fieldKey) {
  const fromBefore = readTestcaseDetailRawField(nav?.before, fieldKey)
  if (fromBefore !== undefined) return fromBefore
  const mods = nav?.modifications
  if (!mods || typeof mods !== 'object') return undefined
  for (const mk of getTestcaseModifyModKeys(fieldKey)) {
    const m = mods[mk]
    if (m != null && typeof m === 'object' && 'old' in m) {
      const v = m.old
      if (normalizeTestcaseModifyFieldKey(fieldKey) === 'execution_result') {
        return v == null ? '' : v
      }
      if (normalizeTestcaseModifyFieldKey(fieldKey) === 'related_defects') {
        return normalizeTestcaseRelatedDefectIds(v)
      }
      if (v != null && String(v).trim() !== '') return v
      if (v === '' && normalizeTestcaseModifyFieldKey(fieldKey) === 'execution_result') {
        return ''
      }
    }
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
  /** 空字符串表示「未执行」，与详情下拉一致，不能显示为「未设置」 */
  if (nk === 'execution_result') {
    return formatTestcaseExecutionResultLabel(raw, t)
  }
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
  if (nk === 'execution_result') return normalizeTestcaseExecutionResultForSelect(raw)
  return raw
}

export function isTestcaseSelectDetailField(fieldKey) {
  return TESTCASE_SELECT_DETAIL_FIELDS.includes(normalizeTestcaseModifyFieldKey(fieldKey))
}

/** 沙箱/详情打开时：有执行结果待采纳则进「执行」Tab，否则留在基本信息 */
export function pickTestcaseEditorTabForPendingModify(modifications) {
  if (!modifications || typeof modifications !== 'object') return null
  for (const [field, data] of Object.entries(modifications)) {
    if (String(field).startsWith('_')) continue
    if (!data || typeof data !== 'object' || !('new' in data) || data.unchanged === true) continue
    const nk = normalizeTestcaseModifyFieldKey(field)
    if (nk === 'execution_result') return 'execution'
  }
  for (const [field, data] of Object.entries(modifications)) {
    if (String(field).startsWith('_')) continue
    if (!data || typeof data !== 'object' || !('new' in data) || data.unchanged === true) continue
    const nk = normalizeTestcaseModifyFieldKey(field)
    if (nk === 'related_defects') return 'defects'
  }
  for (const [field, data] of Object.entries(modifications)) {
    if (String(field).startsWith('_')) continue
    if (!data || typeof data !== 'object' || !('new' in data) || data.unchanged === true) continue
    const nk = normalizeTestcaseModifyFieldKey(field)
    if (
      TESTCASE_DETAIL_FIELDS.includes(nk) &&
      nk !== 'execution_result' &&
      nk !== 'related_defects'
    ) {
      return 'basic'
    }
  }
  return null
}

/**
 * @param {string} fieldKey
 * @param {*} raw
 * @param {{ maxLen?: number, t?: function }} opts
 */
export function formatTestcaseModifyFieldValue(fieldKey, raw, opts = {}) {
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  const maxLen = opts.maxLen ?? 480
  const t = opts.t
  let s = ''
  if (nk === 'steps') {
    s = formatTestcaseStepsForDisplay(raw)
  } else if (nk === 'related_defects') {
    s = formatTestcaseRelatedDefectsForDisplay(raw, { t, titleMap: opts.titleMap })
  } else if (isTestcaseSelectDetailField(nk)) {
    s = formatTestcaseSelectFieldLabel(nk, raw, t)
  } else if (nk === 'append_comment' || nk === 'preconditions') {
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

export function readTestcaseRowField(row, fieldKey, opts = {}) {
  if (!row || typeof row !== 'object') return ''
  const nk = normalizeTestcaseModifyFieldKey(fieldKey)
  const keys = TESTCASE_ROW_ALIASES[nk] || [nk]
  for (const k of keys) {
    if (!Object.prototype.hasOwnProperty.call(row, k)) continue
    const v = row[k]
    if (v == null) continue
    if (Array.isArray(v) && v.length === 0) continue
    if (typeof v === 'string' && v.trim() === '') continue
    return formatTestcaseModifyFieldValue(nk, v, {
      maxLen: 2000,
      t: opts.t,
      titleMap: nk === 'related_defects' ? opts.titleMap : undefined
    })
  }
  return ''
}

/**
 * 测例沙箱/详情：合并 diff 行、before/after、modifications，输出可展示行。
 * @param {object} nav - { target, before, after, modifications }
 * @param {Array} baseRows - 后端 diff 行（可先 normalizeTestcaseSandboxDiffRow）
 * @param {function} t - vue-i18n t
 */
function remapTestcaseSandboxDiffRowForDisplay(row, nav, t) {
  if (!row || typeof row !== 'object') return row
  const mods = nav?.modifications
  const newL = row.lines?.find((l) => l.type === 'add')
  const oldL = row.lines?.find((l) => l.type === 'delete')
  let sample = newL?.content ?? oldL?.content
  if (mods && typeof mods === 'object') {
    const st = mods.status
    const ex = mods.execution_result
    if (ex && typeof ex === 'object') {
      sample = ex.new ?? ex.old ?? sample
    } else if (st && typeof st === 'object') {
      sample = st.new ?? st.old ?? sample
    }
  }
  const fk = remapMislabeledTestcaseSandboxFieldKey(row.field, row.field_label, sample)
  return normalizeTestcaseSandboxDiffRow({ ...row, field: fk }, t)
}

export function enrichTestcaseSandboxDiffRows(nav, baseRows, t, opts = {}) {
  const tgt = String(nav?.target || '')
    .trim()
    .toLowerCase()
  if (tgt !== 'testcase' && tgt !== 'test_case') {
    return Array.isArray(baseRows) ? baseRows : []
  }
  const defectTitleMap = {
    ...buildTestcaseRelatedDefectTitleMap(nav),
    ...(opts.defectTitleMap || {})
  }
  const rows = Array.isArray(baseRows)
    ? baseRows
        .filter((r) => !shouldSuppressMislabeledTestcaseStatusSandboxRow(r, nav))
        .map((r) => remapTestcaseSandboxDiffRowForDisplay(r, nav, t))
    : []
  const before = nav?.before
  const after = nav?.after
  const mods = nav?.modifications
  const seen = new Set(rows.map((r) => normalizeTestcaseModifyFieldKey(r?.field, r?.field_label)))

  const formatSide = (fk, val) =>
    isTestcaseSelectDetailField(fk)
      ? formatTestcaseSelectFieldLabel(fk, val, t)
      : formatTestcaseModifyFieldValue(fk, val, {
          t,
          titleMap: fk === 'related_defects' ? defectTitleMap : undefined
        })

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
    const bo = readTestcaseEffectiveBefore(nav, fk)
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
    if (!TESTCASE_DETAIL_FIELDS.includes(fk)) {
      continue
    }
    const bo = readTestcaseEffectiveBefore(nav, fk)
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
      const bo = readTestcaseEffectiveBefore(nav, fk)
      const ao = readTestcaseModifyNewValue(mods, fk)
      if (ao === undefined) continue
      if (testcaseDetailFieldValuesEqual(fk, bo, ao)) continue
      upsertRow(fk, bo, ao)
    }
  }

  for (let i = 0; i < rows.length; i++) {
    const fk = normalizeTestcaseModifyFieldKey(rows[i]?.field, rows[i]?.field_label)
    if (fk !== 'related_defects') continue
    const bo = readTestcaseEffectiveBefore(nav, fk)
    const ao = readTestcaseEffectiveAfter(nav, fk)
    const oldD = formatTestcaseRelatedDefectsForDisplay(bo, { t, titleMap: defectTitleMap })
    const newD = formatTestcaseRelatedDefectsForDisplay(ao, { t, titleMap: defectTitleMap })
    rows[i] = {
      ...rows[i],
      lines: [
        { type: 'delete', content: oldD, line_no: 0 },
        { type: 'add', content: newD, line_no: 0 }
      ]
    }
  }

  return rows.filter((r) => !shouldSuppressMislabeledTestcaseStatusSandboxRow(r, nav))
}

export function readTestcaseModifySideValue(
  ctx,
  fieldKey,
  rawField,
  fieldLabel,
  which,
  mods = {},
  t = null,
  defectTitleMap = null
) {
  const titleMap =
    defectTitleMap && typeof defectTitleMap === 'object' ? defectTitleMap : {}
  const modSample =
    mods?.execution_result && typeof mods.execution_result === 'object'
      ? which === 'old'
        ? mods.execution_result.old
        : mods.execution_result.new
      : mods?.status && typeof mods.status === 'object'
        ? which === 'old'
          ? mods.status.old
          : mods.status.new
        : null
  const nk = remapMislabeledTestcaseSandboxFieldKey(fieldKey, fieldLabel, modSample)
  const rowReadOpts = {
    t,
    titleMap: nk === 'related_defects' ? titleMap : undefined
  }
  const fromBefore = readTestcaseRowField(ctx?.before, nk, rowReadOpts)
  const fromAfter = readTestcaseRowField(ctx?.after, nk, rowReadOpts)

  if (which === 'old' && fromBefore) return fromBefore
  if (which === 'new' && fromAfter) return fromAfter

  if (which === 'old') {
    const fromEff = readTestcaseEffectiveBefore(ctx, nk)
    if (fromEff !== undefined) {
      const formatted = isTestcaseSelectDetailField(nk)
        ? formatTestcaseSelectFieldLabel(nk, fromEff, t)
        : formatTestcaseModifyFieldValue(nk, fromEff, {
            t,
            titleMap: nk === 'related_defects' ? titleMap : undefined
          })
      if (formatted || nk === 'execution_result' || nk === 'related_defects') return formatted
    }
  }

  const modKeys = getTestcaseModifyModKeys(nk, rawField)
  for (const mk of modKeys) {
    const m = mods[mk]
    if (m == null) continue
    if (typeof m === 'object' && ('old' in m || 'new' in m)) {
      const v = which === 'old' ? m.old : m.new
      const formatted = isTestcaseSelectDetailField(nk)
        ? formatTestcaseSelectFieldLabel(nk, v, t)
        : formatTestcaseModifyFieldValue(nk, v, {
            t,
            titleMap: nk === 'related_defects' ? titleMap : undefined
          })
      if (
        formatted ||
        (nk === 'execution_result' && which === 'old' && (v === '' || v == null)) ||
        (nk === 'related_defects' && which === 'old' && (v == null || (Array.isArray(v) && v.length === 0)))
      ) {
        return formatted
      }
    } else if (which === 'new') {
      const formatted = formatTestcaseModifyFieldValue(nk, m, {
        t,
        titleMap: nk === 'related_defects' ? titleMap : undefined
      })
      if (formatted) return formatted
    }
  }

  return which === 'old' ? fromBefore : fromAfter
}
