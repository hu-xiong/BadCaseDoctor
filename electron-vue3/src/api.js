import axios from 'axios'
import { normalizeUploadImageUrl, uploadResponseToImageUrl } from './utils/uploadImageUrl.js'
import JSONBigInt from 'json-bigint'

const jsonBig = JSONBigInt({ storeAsString: true })

// 开发：空串走 Vite 同源代理。生产 Web：空串走相对路径（nginx 反代）。
// Electron 打包：必须在 .env.production 设置 VITE_BACKEND_URL（勿再默认 localhost）。
const configuredBackend = String(import.meta.env.VITE_BACKEND_URL || '').trim()
export const BACKEND_BASE_URL = configuredBackend || ''

if (
  typeof window !== 'undefined' &&
  !import.meta.env.DEV &&
  !configuredBackend &&
  window.location?.protocol === 'file:'
) {
  console.error('[api] Packaged Electron requires VITE_BACKEND_URL in .env.production')
}

const api = axios.create({
    baseURL: BACKEND_BASE_URL,
    timeout: 30000, // 增加超时时间到30秒
    withCredentials: true, // 如需携带cookie
    transformResponse: [
      (data) => {
        try {
          return jsonBig.parse(data)
        } catch (_e) {
          return data
        }
      }
    ]
})

export { api }

/** URL 路径中的实体 id（雪花 BigInt）：一律字符串 + encode，避免 JS Number 精度丢失 */
export function apiPathId(id) {
  return encodeURIComponent(String(id == null ? '' : id))
}

/** 查询参数中的 plan_id / card_id 等：避免 axios 把大整数序列化成不精确数字 */
function stringifySnowflakeQueryParams(params) {
  const o = { ...(params || {}) }
  const keys = ['plan_id', 'card_id', 'badcase_id', 'bug_id', 'testcase_id', 'baseline_id']
  for (const k of keys) {
    if (o[k] != null && o[k] !== '') o[k] = String(o[k])
  }
  return o
}

// 登录
export function login(data) {
  return api.post('/api/login', data)
}
// 注册
export function register(data) {
  return api.post('/api/register', data)
}
// 获取当前用户
export function getCurrentUser() {
  return api.get('/api/user')
}
/** 预热后端 DB/Redis 连接，避免首条业务接口冷启动（进项目页时调用，勿阻塞 UI） */
export function pingBackend() {
  return api.get('/api/ping', { timeout: 20000 })
}
/** 登录后进项目页时异步预热 ReAct LLM client，勿 await 阻塞 UI */
export function warmupAgent(models) {
  const body = Array.isArray(models) && models.length > 0 ? { models } : {}
  return api.post('/api/agent/warmup', body, { timeout: 30000 })
}
// 发送邮箱验证码
export function sendVerificationCode(data) {
  return api.post('/api/send_verification_code', data)
}

/** 忘记密码：向已注册邮箱发送重置验证码 */
export function forgotPassword(data) {
  return api.post('/api/forgot_password', data)
}

/** 重置密码：email + verification_code + password */
export function resetPassword(data) {
  return api.post('/api/reset_password', data)
}
// 获取项目列表
export function getProjects() {
  return api.get('/api/projects')
}
/** 进入界面后：无项目则从系统模板克隆默认项目副本（勿在登录页 await） */
export function ensureDefaultProject() {
  return api.post('/api/projects/ensure-default', {}, { timeout: 120000 })
}
// 创建项目
export function createProject(data) {
  return api.post('/api/projects', data)
}
// 获取项目详情
export function getProjectDetail(id) {
  return api.get(`/api/projects/${id}`)
}
// 编辑页最小上下文（project + plans + members）；lite=1 跳过计划下各类型计数聚合（编辑下拉不需要）
export function getProjectEditContext(projectId, opts = {}) {
  const params = {}
  if (opts && opts.lite) params.lite = '1'
  return api.get(`/api/projects/${projectId}/edit-context`, { params })
}
// 获取项目BadCase列表（分页）
export function getProjectBadcases(projectId, page = 1, perPage = 10, additionalParams = {}) {
  const params = { page, per_page: perPage, ...stringifySnowflakeQueryParams(additionalParams) }
  return api.get(`/api/projects/${projectId}/badcases`, { params })
}
// 获取项目计划列表
export function getProjectPlans(projectId) {
  return api.get(`/api/projects/${projectId}/plans`)
}
// 获取计划下的Bug列表
export function getPlanBugs(planId) {
  return api.get(`/api/plans/${apiPathId(planId)}/bugs`)
}
// 计划详情（用于新建页补全「所属计划」名称等）
export function getPlanDetail(planId) {
  return api.get(`/api/plans/${apiPathId(planId)}`)
}
// 创建计划
export function createPlan(data) {
  return api.post('/api/plans', data)
}
// 更新计划
export function updatePlan(id, data) {
  return api.put(`/api/plans/${apiPathId(id)}`, data)
}
// 删除计划
export function deletePlan(id) {
  return api.delete(`/api/plans/${apiPathId(id)}`)
}
// 置顶/取消置顶计划
export function pinPlan(id) {
  return api.post(`/api/plans/${apiPathId(id)}/pin`)
}

// 团队管理
export function createTeam(data) {
  return api.post('/api/teams', data)
}

export function addTeamMember(teamId, data) {
  return api.post(`/api/teams/${teamId}/members`, data)
}

export function getProjectTeams(projectId) {
  return api.get(`/api/projects/${projectId}/teams`)
}

export function getProjectMembers(projectId) {
  return api.get(`/api/projects/${projectId}/members`)
}

export function getAvailableUsers() {
  return api.get('/api/users/available')
}

export function addProjectUser(projectId, data) {
  return api.post(`/api/projects/${projectId}/add_user`, data)
}
// 更新项目
export function updateProject(id, data) {
  return api.put(`/api/projects/${id}`, data)
}
// 发布项目
export function publishProject(id) {
  return api.post(`/api/projects/${id}/publish`)
}
// 撤销发布项目
export function revokeProject(id) {
  return api.post(`/api/projects/${id}/revoke`)
}
// 删除项目
export function deleteProject(id) {
  return api.delete(`/api/projects/${id}`)
}

// 上传头像
export function uploadAvatar(file, projectId = null) {
  const formData = new FormData()
  formData.append('file', file)
  
  // 构建URL，包含项目ID参数
  let url = '/api/upload/avatar'
  if (projectId) {
    url += `?project_id=${projectId}`
  }
  
  return api.post(url, formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    timeout: 15000, // 头像上传超时时间15秒
    onUploadProgress: (progressEvent) => {
      // 可以在这里添加上传进度显示
      const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total)
      console.log(`上传进度: ${percentCompleted}%`)
    }
  })
}

// 测试MinIO连接
export function testMinioConnection() {
  return api.get('/api/test/minio')
}
// 新建 BadCase
export function createBadcase(data) {
  return api.post('/api/badcases', data)
}
// 更新 BadCase
export function updateBadcase(id, data) {
  return api.put(`/api/badcases/${apiPathId(id)}`, data)
}
// 获取 BadCase 详情
export function getBadcaseDetail(id) {
  return api.get(`/api/badcases/${apiPathId(id)}`)
}

// 邀请成员
export function inviteMember(project_id, data) {
  return api.post(`/api/projects/${project_id}/invite`, data)
}
// 移除成员
export function removeMember(project_id, user_id) {
  return api.post(`/api/projects/${project_id}/remove`, { user_id })
}
// 更新 BadCase 状态和指派
export function updateBadcaseStatus(id, data) {
  return api.post(`/api/badcases/${apiPathId(id)}/status`, data)
}

// 更新 BadCase 的计划关联
export function updateBadcasePlan(id, planId) {
  return api.put(`/api/badcases/${apiPathId(id)}`, { plan_id: planId != null ? String(planId) : planId })
}
// 添加 BadCase 评论
export function addBadcaseComment(id, data) {
  return api.post(`/api/badcases/${apiPathId(id)}/comment`, data)
}
// 标记 BadCase 已解决
export function closeBadcase(id) {
  return api.post(`/api/badcases/${apiPathId(id)}/close`)
}

// 删除 BadCase
export function deleteBadcase(id) {
  return api.delete(`/api/badcases/${apiPathId(id)}`)
}
// 导入Excel
export function importExcel(formData) {
  return api.post('/api/import_excel', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
}
// 导入数据库
export function importDatabase(data) {
  return api.post('/api/import_database', data)
}

// ==================== Chat Session API ====================

// 获取项目的所有会话（列表接口应很快；略长超时 + 避免与 Agent 长请求共用默认 30s 易误杀）
export function getChatSessions(projectId, opts = {}) {
  const params = {}
  if (opts.limit != null) params.limit = opts.limit
  return api.get(`/api/projects/${apiPathId(projectId)}/chat-sessions`, {
    params,
    timeout: opts.timeout != null ? opts.timeout : 45000
  })
}

// 创建新会话
export function createChatSession(projectId, data) {
  return api.post(`/api/projects/${projectId}/chat-sessions`, data)
}

// 获取会话详情
export function getChatSession(sessionId, params = undefined) {
  return api.get(`/api/chat-sessions/${sessionId}`, { params })
}

// 更新会话
export function updateChatSession(sessionId, data) {
  return api.put(`/api/chat-sessions/${sessionId}`, data)
}

// 生成会话标题
export function generateSessionTitle(sessionId, message) {
  return api.post(`/api/chat-sessions/${sessionId}/generate-title`, { message })
}

// 删除会话
export function deleteChatSession(sessionId) {
  return api.delete(`/api/chat-sessions/${sessionId}`)
}

// 添加消息
export function addChatMessage(sessionId, data) {
  // Agent 消息后 steps/modify_navigation 等 JSON 较大，持久化可能超过默认 30s
  return api.post(`/api/chat-sessions/${sessionId}/messages`, data, { timeout: 120000 })
}

/** 更新助手消息（ReAct 流式 checkpoint / 中断后保留过程） */
export function updateChatMessage(messageId, data) {
  return api.put(`/api/chat-messages/${apiPathId(messageId)}`, data, { timeout: 120000 })
}

/**
 * 聊天附图异步落库：POST /upload（MinIO），返回可公网/内网访问的 url。
 * 勿手动设 Content-Type，以便浏览器带 multipart boundary。
 */
/** 富文本插图：走 /api/upload + 代理 URL，供 RichTextHtmlEditor 使用 */
export function uploadRichTextImageFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/api/upload', fd, { timeout: 120000 }).then((r) => {
    const url = uploadResponseToImageUrl(r)
    if (!url) {
      const d = r?.data
      throw new Error((d && d.error) || 'upload failed')
    }
    return url
  })
}

export function uploadChatImageBlob(blob, filename = 'image.png') {
  const fd = new FormData()
  const name = String(filename || 'image.png').trim() || 'image.png'
  const file =
    blob instanceof File
      ? blob
      : new File([blob], name, { type: blob.type || 'application/octet-stream' })
  fd.append('file', file)
  return api
    .post('/upload', fd, { timeout: 120000 })
    .then((r) => {
      const d = r && r.data !== undefined ? r.data : r
      const url = d && (d.url || d.fileurl || d.filelink)
      if (!url || (d && d.success === false) || (d && d.error)) {
        throw new Error((d && d.error) || 'upload failed')
      }
      return normalizeUploadImageUrl(String(url).trim())
    })
}

/** 列表侧取消删除：清空 DB delete_navigation；采纳：保留快照并标记已确认 */
export function clearChatMessageDeleteNavigation(messageId, opts = {}) {
  return api.post(`/api/chat-messages/${messageId}/clear-delete-navigation`, {
    cancel: opts.cancel === true
  })
}

// ==================== Bug API ====================

// 新建 Bug
export function createBug(data) {
  return api.post('/api/bugs', data)
}

// 更新 Bug
export function updateBug(id, data) {
  return api.put(`/api/bugs/${apiPathId(id)}`, data)
}

// 获取 Bug 详情
export function getBugDetail(id) {
  return api.get(`/api/bugs/${apiPathId(id)}`)
}

// 获取项目 Bug 列表
export function getProjectBugs(projectId, page = 1, perPage = 10, additionalParams = {}) {
  const params = { page, per_page: perPage, ...stringifySnowflakeQueryParams(additionalParams) }
  return api.get(`/api/projects/${projectId}/bugs`, { params })
}

// 更新 Bug 状态
export function updateBugStatus(id, data) {
  return api.post(`/api/bugs/${apiPathId(id)}/status`, data)
}

// 删除 Bug
export function deleteBug(id) {
  return api.delete(`/api/bugs/${apiPathId(id)}`)
}

/** Bug 评论：仅追加；parentId 为回复目标评论 id */
export function addBugComment(bugId, content, messageId = null, parentId = null) {
  const body = { content }
  if (messageId != null) body.message_id = messageId
  if (parentId != null && parentId !== '') body.parent_id = parentId
  return api.post(`/api/bugs/${apiPathId(bugId)}/comment`, body)
}

// ==================== TestCase API ====================

// 创建TestCase
export function createTestCase(data) {
  return api.post('/api/testcases', data)
}

// 更新TestCase
export function updateTestCase(id, data) {
  return api.put(`/api/testcases/${apiPathId(id)}`, data)
}

// 获取TestCase详情
export function getTestCaseDetail(id) {
  return api.get(`/api/testcases/${apiPathId(id)}`)
}

/** 测例评论：仅追加；parentId 为回复目标评论 id */
export function addTestCaseComment(testcaseId, content, messageId = null, parentId = null) {
  const body = { content }
  if (messageId != null) body.message_id = messageId
  if (parentId != null && parentId !== '') body.parent_id = parentId
  return api.post(`/api/testcases/${apiPathId(testcaseId)}/comment`, body)
}

// 删除TestCase
export function deleteTestCase(id) {
  return api.delete(`/api/testcases/${apiPathId(id)}`)
}

// 获取计划下的TestCase数量（与列表统计一致）
export function getPlanTestCaseCount(planId) {
  return api.get(`/api/plans/${apiPathId(planId)}/testcases`, { params: { count_only: 1 } })
}

// 获取计划下的TestCase列表
export function getPlanTestCases(planId) {
  return api.get(`/api/plans/${apiPathId(planId)}/testcases`)
}

// 获取项目的TestCase列表（分页）
export function getProjectTestCases(projectId, page = 1, perPage = 10, params = {}) {
  const merged = stringifySnowflakeQueryParams({ page, per_page: perPage, ...params })
  const queryParams = new URLSearchParams()
  for (const [k, v] of Object.entries(merged)) {
    if (v != null && v !== '') queryParams.set(k, String(v))
  }
  return api.get(`/api/projects/${projectId}/testcases?${queryParams}`)
}

// ==================== 基线 API ====================

// 获取计划的基线列表
export function getPlanBaselines(planId) {
  return api.get(`/api/plans/${apiPathId(planId)}/baselines`)
}

// 创建基线
export function createBaseline(data) {
  return api.post('/api/baselines', data)
}

// 获取基线详情
export function getBaselineDetail(baselineId) {
  return api.get(`/api/baselines/${baselineId}`)
}

// 删除基线
export function deleteBaseline(baselineId) {
  return api.delete(`/api/baselines/${baselineId}`)
}

// 站内工作流通知（与邮件/CLI 同源落库）
export function getWorkflowNotifications(params = {}) {
  return api.get('/api/notifications', { params })
}

export function markWorkflowNotificationRead(id) {
  return api.post(`/api/notifications/${id}/read`)
}

export function markAllWorkflowNotificationsRead(params = {}) {
  return api.post('/api/notifications/mark-all-read', null, { params })
}

// ==================== Agent API ====================

// 执行通用 Agent
export function executeAgent(data) {
  return api.post('/api/agent/execute', data)
}

// 保存 Agent 生成的 Bug
export function saveAgentBugs(data) {
  return api.post('/api/agent/save-bugs', data)
}

// ==================== 快速命令 API ====================

export function getQuickCommands(projectId = null) {
  const params = projectId ? { project_id: projectId } : {}
  return api.get('/api/terminal/quick-commands', { params })
}

export function createQuickCommand(data) {
  return api.post('/api/terminal/quick-commands', data)
}

export function deleteQuickCommand(id) {
  return api.delete(`/api/terminal/quick-commands/${id}`)
}

// ==================== Card API ====================

// 创建卡片
export function createCard(data) {
  return api.post('/api/cards', data)
}

// 获取项目卡片列表
export function getProjectCards(projectId, page = 1, perPage = 10, additionalParams = {}) {
  const params = { page, per_page: perPage, ...stringifySnowflakeQueryParams(additionalParams) }
  return api.get(`/api/projects/${projectId}/cards`, { params })
}

/** 按源表类型 + 源表主键解析 Card（不按 plan 分页过滤；用于行上缺 card_id 时挂 type-list Tab） */
export function resolveProjectCardBySource(projectId, params = {}) {
  return api.get(`/api/projects/${projectId}/cards/resolve-source`, {
    params: stringifySnowflakeQueryParams(params)
  })
}

// 获取卡片详情
export function getCardDetail(cardId) {
  return api.get(`/api/cards/${apiPathId(cardId)}`)
}

// 更新卡片
export function updateCard(cardId, data) {
  return api.put(`/api/cards/${apiPathId(cardId)}`, data)
}

// 删除卡片（Bug/BadCase/TestCase 类型可能返回 409 要求二次确认级联删除源表）
export function deleteCard(cardId, opts = {}) {
  const axiosOpts = {
    validateStatus: (status) => (status >= 200 && status < 300) || status === 409
  }
  const body = {}
  if (opts && opts.confirm_cascade_sources === true) {
    body.confirm_cascade_sources = true
  }
  if (opts && opts.confirm_cascade_badcases === true) {
    body.confirm_cascade_badcases = true
  }
  if (opts && opts.confirm_cascade_bugs === true) {
    body.confirm_cascade_bugs = true
  }
  if (opts && opts.confirm_cascade_testcases === true) {
    body.confirm_cascade_testcases = true
  }
  if (Object.keys(body).length) {
    axiosOpts.data = body
  }
  return api.delete(`/api/cards/${apiPathId(cardId)}`, axiosOpts)
}

const CASCADE_CARD_DELETE_CODES = new Set([
  'CASCADE_CARD_SOURCES_REQUIRED',
  'CASCADE_BADCASES_REQUIRED' // 兼容旧后端
])

/** 若服务端要求级联删除源表，先调 confirmFn(payload) 再重试；取消则返回 data.cancelled */
export async function deleteCardWithCascadeConfirm(cardId, options = {}) {
  const { confirmFn } = options
  let res = await deleteCard(cardId)
  if (res.status === 409 && res.data && CASCADE_CARD_DELETE_CODES.has(res.data.code)) {
    if (typeof confirmFn !== 'function') {
      return res
    }
    const ok = await Promise.resolve(confirmFn(res.data))
    if (!ok) {
      return {
        status: 409,
        data: { ...res.data, success: false, cancelled: true }
      }
    }
    res = await deleteCard(cardId, { confirm_cascade_sources: true })
  }
  return res
}

/** 二次确认文案：与 CardPanel / ProjectDetail 等共用（需传入 vue-i18n 的 t） */
export function cascadeCardDeleteConfirmText(t, payload) {
  const sk = (payload && payload.source_kind) || 'badcase'
  const n = (payload && payload.count) ?? 0
  const key =
    sk === 'bug'
      ? 'unplannedCards.cascadeBugSecondConfirm'
      : sk === 'testcase'
        ? 'unplannedCards.cascadeTestcaseSecondConfirm'
        : 'unplannedCards.cascadeBadcaseSecondConfirm'
  const head = typeof t === 'function' ? t(key, { count: n }) : key
  const raw =
    (payload && payload.linked_items) ||
    (payload && payload.linked_badcases) ||
    (payload && payload.linked_bugs) ||
    (payload && payload.linked_testcases) ||
    []
  const lines = raw.map((x) => x.title || x.id).slice(0, 12)
  const titles = lines.join('\n')
  const suffix = n > 12 ? '\n…' : ''
  return `${head}\n\n${titles}${suffix}`
}

// 项目内全局搜索（计划 + 卡片 + BadCase + Bug + 测试用例）
export function globalSearch(projectId, query, perType = 30) {
  return api.get(`/api/projects/${projectId}/global-search`, {
    params: { query, per_type: perType }
  })
}

// 全局搜索卡片
export function searchCards(params) {
  const { query, types = 'bug,badcase,testcase', project_id, page = 1, per_page = 20 } = params
  const configParams = { query, types, page, per_page }
  if (project_id) configParams.project_id = project_id
  return api.get('/api/cards/search', { params: configParams })
}

// 移动卡片到指定计划
export function moveCard(cardId, planId) {
  return api.post(`/api/cards/${apiPathId(cardId)}/move`, {
    plan_id: planId != null && planId !== '' ? String(planId) : planId
  })
}

// 获取卡片类型列表
export function getCardTypes(projectId) {
  return api.get('/api/card-types', { params: { project_id: projectId } })
}

// 创建卡片类型
export function createCardType(data) {
  return api.post('/api/card-types', data)
}

// 更新卡片类型
export function updateCardType(typeId, data) {
  return api.put(`/api/card-types/${typeId}`, data)
}

// 删除卡片类型
export function deleteCardType(typeId) {
  return api.delete(`/api/card-types/${typeId}`)
}

// 获取卡片计划关联关系
export function getCardPlanRelations(params) {
  return api.get('/api/card-plan-relations', { params })
}

// 创建卡片计划关联
export function createCardPlanRelation(data) {
  return api.post('/api/card-plan-relations', data)
}

// 删除卡片计划关联
export function deleteCardPlanRelation(relationId) {
  return api.delete(`/api/card-plan-relations/${relationId}`)
}

// 获取卡片计划变更历史
export function getCardPlanHistory(cardId) {
  return api.get(`/api/cards/${apiPathId(cardId)}/history`)
}

export default api 
