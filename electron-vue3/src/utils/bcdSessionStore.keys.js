/**
 * sessionStorage 键常量（对齐 docs/需求文档_sessionStorage会话与任务状态管理.md §5）
 */

export const BCD_SS_SCHEMA_VERSION = 1
export const BCD_SS_PREFIX = 'bcd:ss:'

export const projectSessionKey = (projectId) =>
  `${BCD_SS_PREFIX}project:${projectId != null && projectId !== '' ? String(projectId) : '0'}`

export const agentRunKey = (projectId, sessionId) =>
  `${BCD_SS_PREFIX}agent:${String(projectId)}:${String(sessionId)}`

/** Agent 续流 UI 快照（与 meta 分键，避免 lastSeq 节流写时重复 stringify 大对象） */
export const agentRunSnapshotKey = (projectId, sessionId) =>
  `${BCD_SS_PREFIX}agent-snap:${String(projectId)}:${String(sessionId)}`

export const diffBridgeKey = (projectId) => `${BCD_SS_PREFIX}diff:${String(projectId)}`

/** @deprecated 使用 tabIndexKey(userId, projectId) */
export const workbenchKey = (projectId) => `${BCD_SS_PREFIX}workbench:${String(projectId)}`

/** 工作台 Tab 条 + 当前激活（每用户每项目） */
export const tabIndexKey = (userId, projectId) =>
  `${BCD_SS_PREFIX}tabindex:${String(userId)}:${String(projectId)}`

/** 单个工作台 Tab 文档（视图 + pending 展示镜像） */
export const tabDocKey = (userId, projectId, workbenchTabId) =>
  `${BCD_SS_PREFIX}tabdoc:${String(userId)}:${String(projectId)}:${String(workbenchTabId)}`

export const createHoldKey = (projectId, sessionId) => {
  const pid = projectId != null && projectId !== '' ? String(projectId) : '0'
  const sid =
    sessionId != null && sessionId !== '' && sessionId !== undefined
      ? String(sessionId)
      : '_none_'
  return `${BCD_SS_PREFIX}create-hold:${pid}:${sid}`
}

/** @deprecated M0 迁移用，禁止新写入 */
export const LEGACY_PENDING_MODIFY_DIFF = 'pendingModifyDiff'
