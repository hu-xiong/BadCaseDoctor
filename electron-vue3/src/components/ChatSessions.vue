<template>
  <div class="chat-sessions-container">
    <!-- 导航栏 -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
      <div class="container-fluid">
        <div class="navbar-nav">
          <a class="nav-link" href="#" @click="$router.push('/project-manage')">
            <i class="bi bi-arrow-left me-1"></i>
            返回仪表板
          </a>
        </div>
        <a class="navbar-brand" href="#">
          <i class="bi bi-chat-dots me-2"></i>
          AI助手对话
        </a>
        <div class="navbar-nav ms-auto">
          <div class="nav-item dropdown">
            <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
              <i class="bi bi-person-circle me-1"></i>
              {{ user?.name || '用户' }}
            </a>
            <ul class="dropdown-menu">
              <li><a class="dropdown-item" href="#" @click="logout">退出登录</a></li>
            </ul>
          </div>
        </div>
      </div>
    </nav>

    <div class="container-fluid mt-4">
      <div class="row">
        <!-- 左侧会话列表 -->
        <div class="col-md-3">
          <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
              <h5 class="card-title mb-0">
                <i class="bi bi-chat-square-text me-2"></i>
                会话列表
              </h5>
              <button 
                class="btn btn-primary btn-sm" 
                @click="createNewSession"
                title="新建会话"
              >
                <i class="bi bi-plus-lg"></i>
              </button>
            </div>
            <div class="card-body p-0">
              <div class="sessions-list">
                <div 
                  v-for="session in sessions" 
                  :key="session.id"
                  :class="[
                    'session-item', 
                    currentSession?.id === session.id ? 'active' : ''
                  ]"
                  @click="selectSession(session)"
                >
                  <div class="session-info">
                    <div class="session-name">
                      <i class="bi bi-chat-dots me-2"></i>
                      {{ session.name }}
                    </div>
                    <div class="session-time">
                      {{ formatSessionTime(session.updated_at) }}
                    </div>
                  </div>
                  <div class="session-actions">
                    <button 
                      class="btn btn-sm btn-link text-danger p-0"
                      @click.stop="deleteSession(session.id)"
                      title="删除会话"
                    >
                      <i class="bi bi-trash"></i>
                    </button>
                  </div>
                </div>
                
                <div v-if="sessions.length === 0" class="text-center p-3 text-muted">
                  <i class="bi bi-chat-square fs-4"></i>
                  <p class="mb-0">暂无会话</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 右侧聊天区域 -->
        <div class="col-md-9">
          <div class="card h-100">
            <div class="card-header" v-if="currentSession">
              <h5 class="card-title mb-0">
                <i class="bi bi-chat-dots me-2"></i>
                {{ currentSession.name }}
              </h5>
            </div>
            <div class="card-body" v-if="currentSession">
              <SimpleChatPanel 
                :session-id="currentSession.id"
                :project-id="selectedProject"
              />
            </div>
            
            <!-- 空状态 -->
            <div class="card-body d-flex align-items-center justify-content-center" v-else>
              <div class="text-center">
                <i class="bi bi-chat-dots fs-1 text-muted"></i>
                <h5 class="text-muted mt-3">选择一个会话开始对话</h5>
                <p class="text-muted">点击左侧"+"按钮创建新会话</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import SimpleChatPanel from './SimpleChatPanel.vue'
import { getChatSessions, createChatSession, deleteChatSession } from '../api.js'
import user, { logout } from '../store/user.js'
import {
  removeSessionFromProjectCache,
  clearCreateHold,
  clearAgentRun,
  clearDiffSlotsForSession
} from '../utils/bcdSessionStore.js'

const router = useRouter()
const route = useRoute()

// 状态
const sessions = ref([])
const currentSession = ref(null)
const selectedProject = ref(null)

// 从路由参数获取项目ID
const loadProjectId = () => {
  const projectId = route.params.projectId
  if (projectId) {
    selectedProject.value = parseInt(projectId)
  } else {
    // 如果没有项目ID，可以从 localStorage 或其他方式获取
    const lastProjectId = localStorage.getItem('lastProjectId')
    if (lastProjectId) {
      selectedProject.value = parseInt(lastProjectId)
    }
  }
}

// 加载会话列表
const loadSessions = async () => {
  if (!selectedProject.value) return
  try {
    const response = await getChatSessions(selectedProject.value)
    if (response.data.success) {
      sessions.value = response.data.sessions
      // 如果没有当前会话且有会话列表，选择第一个
      if (!currentSession.value && sessions.value.length > 0) {
        selectSession(sessions.value[0])
      }
    }
  } catch (error) {
    console.error('加载会话列表失败:', error)
  }
}

// 创建新会话
const createNewSession = async () => {
  if (!selectedProject.value) return
  try {
    const sessionName = `newchat ${new Date().toLocaleTimeString()}`
    const response = await createChatSession(selectedProject.value, { name: sessionName })
    if (response.data.success) {
      const newSession = response.data.session
      sessions.value.unshift(newSession)
      selectSession(newSession)
    }
  } catch (error) {
    console.error('创建会话失败:', error)
    alert('创建会话失败，请重试')
  }
}

// 选择会话
const selectSession = (session) => {
  currentSession.value = session
}

// 删除会话
const deleteSession = async (sessionId) => {
  if (!confirm('确定要删除这个会话吗？此操作无法撤销。')) {
    return
  }
  
  try {
    const response = await deleteChatSession(sessionId)
    if (response.data.success) {
      const pid = selectedProject.value
      if (pid) {
        removeSessionFromProjectCache(pid, sessionId)
        clearCreateHold(pid, sessionId)
        clearAgentRun(pid, sessionId)
        clearDiffSlotsForSession(pid, sessionId)
      }
      // 从列表中移除
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      // 如果删除的是当前会话，选择下一个会话或置空
      if (currentSession.value?.id === sessionId) {
        if (sessions.value.length > 0) {
          selectSession(sessions.value[0])
        } else {
          currentSession.value = null
        }
      }
    }
  } catch (error) {
    console.error('删除会话失败:', error)
    alert('删除会话失败，请重试')
  }
}

// 格式化会话时间
const formatSessionTime = (timestamp) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now - date
  
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor(diff / (1000 * 60 * 60))
  const minutes = Math.floor(diff / (1000 * 60))
  
  if (days > 0) {
    return `${days}天前`
  } else if (hours > 0) {
    return `${hours}小时前`
  } else if (minutes > 0) {
    return `${minutes}分钟前`
  } else {
    return '刚刚'
  }
}

onMounted(() => {
  loadProjectId()
  loadSessions()
})
</script>

<style scoped>
.chat-sessions-container {
  min-height: 100vh;
  background-color: #f8f9fa;
}

.sessions-list {
  max-height: 600px;
  overflow-y: auto;
}

.session-item {
  display: flex;
  justify-content: between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  transition: background-color 0.2s;
}

.session-item:hover {
  background-color: #f5f5f5;
}

.session-item.active {
  background-color: #e3f2fd;
  border-right: 3px solid #2196f3;
}

.session-info {
  flex: 1;
}

.session-name {
  font-weight: 500;
  color: #333;
  margin-bottom: 2px;
}

.session-time {
  font-size: 12px;
  color: #666;
}

.session-actions {
  margin-left: 8px;
}

.card {
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.navbar {
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
</style>