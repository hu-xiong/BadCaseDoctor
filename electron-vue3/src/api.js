import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:5000', // TODO: 根据后端实际端口调整
  timeout: 30000, // 增加超时时间到30秒
  withCredentials: true // 如需携带cookie
})

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
// 发送邮箱验证码
export function sendVerificationCode(data) {
  return api.post('/api/send_verification_code', data)
}
// 获取项目列表
export function getProjects() {
  return api.get('/api/projects')
}
// 创建项目
export function createProject(data) {
  return api.post('/api/projects', data)
}
// 获取项目详情
export function getProjectDetail(id) {
  return api.get(`/api/projects/${id}`)
}
// 获取项目BadCase列表（分页）
export function getProjectBadcases(projectId, page = 1, perPage = 10, additionalParams = {}) {
  const params = { page, per_page: perPage, ...additionalParams }
  return api.get(`/api/projects/${projectId}/badcases`, { params })
}
// 获取项目计划列表
export function getProjectPlans(projectId) {
  return api.get(`/api/projects/${projectId}/plans`)
}
// 获取计划下的Bug列表
export function getPlanBugs(planId) {
  return api.get(`/api/plans/${planId}/bugs`)
}
// 创建计划
export function createPlan(data) {
  return api.post('/api/plans', data)
}
// 更新计划
export function updatePlan(id, data) {
  return api.put(`/api/plans/${id}`, data)
}
// 删除计划
export function deletePlan(id) {
  return api.delete(`/api/plans/${id}`)
}
// 置顶/取消置顶计划
export function pinPlan(id) {
  return api.post(`/api/plans/${id}/pin`)
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
  return api.put(`/api/badcases/${id}`, data)
}
// 获取 BadCase 详情
export function getBadcaseDetail(id) {
  return api.get(`/api/badcases/${id}`)
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
  return api.post(`/api/badcases/${id}/status`, data)
}

// 更新 BadCase 的计划关联
export function updateBadcasePlan(id, planId) {
  return api.put(`/api/badcases/${id}`, { plan_id: planId })
}
// 添加 BadCase 评论
export function addBadcaseComment(id, data) {
  return api.post(`/api/badcases/${id}/comment`, data)
}
// 标记 BadCase 已解决
export function closeBadcase(id) {
  return api.post(`/api/badcases/${id}/close`)
}
// 导入Excel
export function importExcel(formData) {
  return api.post('/api/import_excel', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
}
// 导入数据库
export function importDatabase(data) {
  return api.post('/api/import_database', data)
}

// 执行终端命令
export function executeTerminalCommand(payload) {
  // payload: { command: string, cwd?: string, timeout?: number, session_id?: string }
  return api.post('/api/terminal/exec', payload)
}

// 终止终端会话
export function killTerminalSession(sessionId = 'default') {
  return api.post('/api/terminal/kill', { session_id: sessionId })
}

// 获取终端会话状态
export function getTerminalStatus(sessionId = 'default') {
  return api.get(`/api/terminal/status?session_id=${sessionId}`)
}

// ==================== Chat Session API ====================

// 获取项目的所有会话
export function getChatSessions(projectId) {
  return api.get(`/api/projects/${projectId}/chat-sessions`)
}

// 创建新会话
export function createChatSession(projectId, data) {
  return api.post(`/api/projects/${projectId}/chat-sessions`, data)
}

// 获取会话详情
export function getChatSession(sessionId) {
  return api.get(`/api/chat-sessions/${sessionId}`)
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
  return api.post(`/api/chat-sessions/${sessionId}/messages`, data)
}

// ==================== Bug API ====================

// 新建 Bug
export function createBug(data) {
  return api.post('/api/bugs', data)
}

// 更新 Bug
export function updateBug(id, data) {
  return api.put(`/api/bugs/${id}`, data)
}

// 获取 Bug 详情
export function getBugDetail(id) {
  return api.get(`/api/bugs/${id}`)
}

// 获取项目 Bug 列表
export function getProjectBugs(projectId, page = 1, perPage = 10, additionalParams = {}) {
  const params = { page, per_page: perPage, ...additionalParams }
  return api.get(`/api/projects/${projectId}/bugs`, { params })
}

// 更新 Bug 状态
export function updateBugStatus(id, data) {
  return api.post(`/api/bugs/${id}/status`, data)
}

// 删除 Bug
export function deleteBug(id) {
  return api.delete(`/api/bugs/${id}`)
}

// ==================== TestCase API ====================

// 创建TestCase
export function createTestCase(data) {
  return api.post('/api/testcases', data)
}

// 更新TestCase
export function updateTestCase(id, data) {
  return api.put(`/api/testcases/${id}`, data)
}

// 获取TestCase详情
export function getTestCaseDetail(id) {
  return api.get(`/api/testcases/${id}`)
}

// 删除TestCase
export function deleteTestCase(id) {
  return api.delete(`/api/testcases/${id}`)
}

// 获取计划下的TestCase列表
export function getPlanTestCases(planId) {
  return api.get(`/api/plans/${planId}/testcases`)
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

export default api 