/**
 * Bug和BadCase状态枚举定义
 * 与后端保持严格一致
 */

// Bug状态枚举
export const BugStatus = {
  NEW: 'new',
  REOPENED: 'reopened',
  CLOSED: 'closed',
  RESOLVED: 'resolved',
  HOLD: 'hold',
  NOT_A_BUG: 'not_a_bug',
  NEW_FEATURE: 'new_feature'
}

// Bug状态显示文本
export const BugStatusText = {
  [BugStatus.NEW]: '新建',
  [BugStatus.REOPENED]: 'reopened',
  [BugStatus.CLOSED]: 'closed',
  [BugStatus.RESOLVED]: 'resolved',
  [BugStatus.HOLD]: 'hold',
  [BugStatus.NOT_A_BUG]: 'not_a_bug',
  [BugStatus.NEW_FEATURE]: 'new_feature'
}

// BadCase状态枚举
export const BadCaseStatus = {
  NEW: 'new',
  PENDING: 'pending',
  REOPENED: 'reopened',
  CLOSED: 'closed',
  RESOLVED: 'resolved',
  HOLD: 'hold',
  NOT_BADCASE: 'not_badcase'
}

// BadCase状态显示文本
export const BadCaseStatusText = {
  [BadCaseStatus.NEW]: '新建',
  [BadCaseStatus.PENDING]: 'pending',
  [BadCaseStatus.REOPENED]: 'reopened',
  [BadCaseStatus.CLOSED]: 'closed',
  [BadCaseStatus.RESOLVED]: 'resolved',
  [BadCaseStatus.HOLD]: 'hold',
  [BadCaseStatus.NOT_BADCASE]: 'not_badcase'
}

// 测试用例状态枚举
export const TestCaseStatus = {
  DRAFT: 'draft',       // 草稿
  REVIEW: 'review',     // 规绩
  ACTIVE: 'active',     // 生效
  ARCHIVED: 'archived'  // 归档
}

// 测试用例状态显示文本
export const TestCaseStatusText = {
  [TestCaseStatus.DRAFT]: '草稿',
  [TestCaseStatus.REVIEW]: '规绩',
  [TestCaseStatus.ACTIVE]: '生效',
  [TestCaseStatus.ARCHIVED]: '归档'
}

// 执行结果枚举
export const ExecutionResult = {
  PASS: 'pass',
  FAIL: 'fail',
  BLOCKED: 'blocked',
  SKIP: 'skip'
}

// 执行结果显示文本
export const ExecutionResultText = {
  [ExecutionResult.PASS]: '通过',
  [ExecutionResult.FAIL]: '失败',
  [ExecutionResult.BLOCKED]: '阻塞',
  [ExecutionResult.SKIP]: '跳过'
}

// 状态验证函数
export function isValidBugStatus(status) {
  return Object.values(BugStatus).includes(status)
}

export function isValidBadCaseStatus(status) {
  return Object.values(BadCaseStatus).includes(status)
}

export function isValidTestCaseStatus(status) {
  return Object.values(TestCaseStatus).includes(status)
}

export function isValidExecutionResult(result) {
  return Object.values(ExecutionResult).includes(result)
}

// 获取状态显示文本
export function getBugStatusText(status) {
  return BugStatusText[status] || status
}

export function getBadCaseStatusText(status) {
  return BadCaseStatusText[status] || status
}

export function getTestCaseStatusText(status) {
  return TestCaseStatusText[status] || status
}

export function getExecutionResultText(result) {
  return ExecutionResultText[result] || result
}
