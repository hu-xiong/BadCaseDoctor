/**
 * 报告/任务运行状态展示工具：cdp_test_runs 与 react_agent_runs 的状态枚举合流。
 * i18n 文案走 reportsPanel.status.*，样式走 st-* 类（组件内定义颜色）。
 */

export const REPORT_STATUS_KEY_MAP = {
  running: 'running',
  passed: 'passed',
  partial: 'partial',
  blocked: 'blocked',
  completed: 'completed',
  done: 'completed',
  cancelled: 'cancelled',
  interrupted: 'cancelled',
  failed: 'failed',
  timeout: 'failed'
}

export function reportStatusKey(status) {
  return REPORT_STATUS_KEY_MAP[String(status || '').toLowerCase()] || ''
}

export function reportStatusLabel(t, status) {
  const k = reportStatusKey(status)
  return k ? t('reportsPanel.status.' + k) : String(status || '')
}

export function reportStatusClass(status) {
  return 'st-' + (reportStatusKey(status) || 'unknown')
}
