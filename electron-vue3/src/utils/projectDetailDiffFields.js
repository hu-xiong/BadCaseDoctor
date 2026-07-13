/** ProjectDetail 修改 diff 字段常量与归一化（自 ProjectDetail.vue 拆出） */

export const DETAIL_FIELDS = [
  'base_problem',
  'reproduction_steps',
  'answer',
  'correct_answer',
  'badcase_result',
  'solution',
  'problem_reason',
  'steps_to_reproduce',
  'expected_result',
  'actual_result',
  'preconditions',
  'steps',
  'reproduce_steps',
  'priority',
  'case_category',
  'severity',
  'case_type',
  'test_type',
  'execution_result',
  'related_defects',
  'append_comment',
  'plan_id',
  'project_id'
]

export const FIELD_LABELS = {
  title: '标题',
  status: '状态',
  priority: '优先级',
  case_category: '问题分类',
  severity: '严重级别',
  assignee: '负责人',
  base_problem: '相似问题',
  reproduction_steps: '复现步骤',
  answer: '答案',
  correct_answer: '正确答案',
  badcase_result: 'BadCase结果',
  solution: '解决方式',
  problem_reason: '问题原因',
  steps_to_reproduce: '复现步骤',
  expected_result: '期望结果',
  actual_result: '实际结果',
  preconditions: '前置条件',
  steps: '测试步骤',
  case_type: '用例类型',
  test_type: '测试类型',
  execution_result: '执行结果',
  related_defects: '关联缺陷',
  append_comment: '追加评论',
  plan_id: '所属计划',
  project_id: '所属项目'
}

export const LABEL_TO_FIELD = (() => {
  const map = {}
  Object.entries(FIELD_LABELS).forEach(([key, label]) => {
    map[label] = key
  })
  map['期望结果'] = 'expected_result'
  map.similar_questions = 'base_problem'
  map.similar_question = 'base_problem'
  ;['Owner', 'owner', 'Assignee', 'assignee'].forEach((k) => {
    map[k] = 'assignee'
  })
  ;['工作流状态', '处理状态', 'Case状态', '用例状态', '缺陷状态'].forEach((k) => {
    map[k] = 'status'
  })
  return map
})()

export const LIST_FIELDS = ['title', 'status', 'assignee']

/** diff 行字段名归一化 */
export function normalizeDiffFieldKey(rawField, optTarget = null) {
  const tgt = String(optTarget || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_')
  const raw = rawField ?? ''
  if (typeof raw === 'string') {
    const t = raw.trim()
    const tl = t.toLowerCase().replace(/-/g, '_')
    if (tl === 'remark') return 'append_comment'
    if (['badcase', 'bad_case'].includes(tgt)) {
      const tlcf = t.toLowerCase().replace(/-/g, '_')
      if (
        tlcf === 'classification' ||
        tlcf === 'category' ||
        t === '问题分类' ||
        (t.includes('问题分类') && !t.includes('优先级'))
      ) {
        return 'case_category'
      }
      if (
        t === '严重程度' ||
        t === '严重级别' ||
        t.includes('严重程度') ||
        (t.includes('严重') && !t.includes('优先级'))
      ) {
        return 'priority'
      }
      if (t === '复现步骤' || t.includes('复现步骤')) {
        return 'reproduction_steps'
      }
      const badcaseFieldAliases = {
        similar_questions: 'base_problem',
        similar_question: 'base_problem',
        related_questions: 'base_problem',
        related_problem: 'base_problem',
        specific_problem: 'base_problem',
        concrete_problem: 'base_problem',
        problem_description: 'base_problem',
        reproduce_steps: 'reproduction_steps',
        reproduction_step: 'reproduction_steps',
        badcase_reproduction_steps: 'reproduction_steps',
        steps_to_reproduce: 'reproduction_steps',
        steps: 'reproduction_steps'
      }
      if (Object.prototype.hasOwnProperty.call(badcaseFieldAliases, tlcf)) {
        return badcaseFieldAliases[tlcf]
      }
    }
    if (tgt === 'bug') {
      if (t === '严重级别' || t === '严重程度' || t.includes('严重级别') || t.includes('严重程度')) {
        return 'severity'
      }
      if (t === '备注' || t === '评论' || t.includes('追加评论') || t.includes('添加评论')) {
        return 'append_comment'
      }
      if (t === '复现步骤' || t.includes('复现步骤')) {
        return 'steps_to_reproduce'
      }
      const bugReproAliases = {
        reproduction_steps: 'steps_to_reproduce',
        reproduce_steps: 'steps_to_reproduce',
        repro_steps: 'steps_to_reproduce',
        steps: 'steps_to_reproduce'
      }
      if (Object.prototype.hasOwnProperty.call(bugReproAliases, tl)) {
        return bugReproAliases[tl]
      }
    }
    if (['badcase', 'bad_case'].includes(tgt)) {
      if (t === '备注' || t === '评论' || t.includes('追加评论') || t.includes('添加评论')) {
        return 'append_comment'
      }
    }
    if (['testcase', 'test_case'].includes(tgt)) {
      if (t === '严重程度' || t.includes('严重程度')) return 'priority'
      if (t === '用例类型' || t.includes('用例类型')) return 'case_type'
      if (t === '测试类型' || t.includes('测试类型')) return 'test_type'
      const tlTc = t.toLowerCase().replace(/-/g, '_')
      if (tlTc === 'testcase_type' || tlTc === 'test_case_type') return 'case_type'
      if (t === '测试步骤' || t === '用例步骤' || t.includes('测试步骤')) return 'steps'
      if (t === '备注') return 'append_comment'
      if (t === '前置条件') return 'preconditions'
      if (t === '执行结果' || t.includes('执行结果')) return 'execution_result'
      if (t === '关联缺陷' || t.includes('关联缺陷')) return 'related_defects'
      if (t === '评论' || t.includes('追加评论') || t.includes('添加评论')) return 'append_comment'
      if (t === '所属计划' || t.includes('所属计划') || t === '所属迭代') return 'plan_id'
      if (t === '所属项目' || t.includes('所属项目') || t === '项目名称') return 'project_id'
    }
    if (Object.prototype.hasOwnProperty.call(LABEL_TO_FIELD, t)) {
      const m = LABEL_TO_FIELD[t]
      return m === 'assignee_id' ? 'assignee' : m
    }
    const snakeAliases = {
      case_status: 'status',
      workflow_status: 'status',
      badcase_status: 'status',
      bug_status: 'status',
      testcase_status: 'status',
      test_status: 'status',
      record_status: 'status'
    }
    if (Object.prototype.hasOwnProperty.call(snakeAliases, tl)) {
      return snakeAliases[tl]
    }
  }
  const mapped = LABEL_TO_FIELD[raw] || raw
  return mapped === 'assignee_id' ? 'assignee' : mapped
}

export function filterModifyDataToListOverlay(modifyData, optTarget = null) {
  const md = modifyData && typeof modifyData === 'object' ? modifyData : {}
  const out = {}
  for (const [fk, v] of Object.entries(md)) {
    if (String(fk).startsWith('_')) continue
    const nk = normalizeDiffFieldKey(fk, optTarget)
    if (!LIST_FIELDS.includes(nk)) continue
    if (!v || typeof v !== 'object' || !('new' in v) || v.unchanged === true) continue
    out[nk] = v
  }
  return out
}

export function filterModifyDataToDetailSession(modifyData, optTarget = null) {
  const md = modifyData && typeof modifyData === 'object' ? modifyData : {}
  const out = {}
  for (const [fk, v] of Object.entries(md)) {
    if (String(fk).startsWith('_')) continue
    const nk = normalizeDiffFieldKey(fk, optTarget)
    if (!DETAIL_FIELDS.includes(nk)) continue
    if (!v || typeof v !== 'object' || !('new' in v) || v.unchanged === true) continue
    out[nk] = v
  }
  return out
}
