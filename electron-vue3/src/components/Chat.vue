<template>
  <div class="chat">
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
          AI助手
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
        <!-- 聊天区域 -->
        <div class="col-md-8">
          <div class="card h-100">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-chat-dots me-2"></i>
                与AI助手对话
              </h5>
            </div>
            <div class="card-body d-flex flex-column" style="height: 600px;">
              <!-- 消息列表 -->
              <div class="flex-grow-1 overflow-auto mb-3" ref="messageContainer">
                <div v-if="messages.length === 0" class="text-center py-5">
                  <i class="bi bi-chat-dots fs-1 text-muted"></i>
                  <p class="text-muted mt-2">开始与AI助手对话吧</p>
                </div>
                
                <div v-else>
                  <div v-for="message in messages" :key="message.id" class="message-item mb-3">
                    <div :class="message.role === 'user' ? 'message-user' : 'message-assistant'">
                      <div class="message-avatar">
                        <i :class="message.role === 'user' ? 'bi bi-person-circle' : 'bi bi-robot'"></i>
                      </div>
                      <div class="message-content">
                        <div class="message-header">
                          <span class="message-name">{{ message.role === 'user' ? '您' : 'AI助手' }}</span>
                          <small class="message-time">{{ formatTime(message.timestamp) }}</small>
                        </div>
                        <!-- 使用打字机效果显示内容 -->
                        <div v-if="message.role === 'assistant'" class="message-text-typewriter">
                          <TypewriterText 
                            :text="message.content" 
                            :speed="30"
                            :autoPlay="true"
                          />
                        </div>
                        <div v-else class="message-text">
                          <pre class="mb-0">{{ message.content }}</pre>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <!-- 输入区域 -->
              <div class="border-top pt-3">
                <div class="input-group">
                  <textarea
                    class="form-control"
                    v-model="inputMessage"
                    @keydown.ctrl.enter="sendMessage"
                    placeholder="输入您的消息... (Ctrl+Enter 发送)"
                    rows="3"
                    :disabled="sending"
                  ></textarea>
                  <button
                    class="btn btn-primary"
                    @click="sendMessage"
                    :disabled="sending || !inputMessage.trim()"
                  >
                    <span v-if="sending" class="spinner-border spinner-border-sm me-2"></span>
                    <i v-else class="bi bi-send me-2"></i>
                    {{ sending ? '发送中...' : '发送' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 工具面板 -->
        <div class="col-md-4">
          <div class="card h-100">
            <div class="card-header">
              <h5 class="card-title mb-0">
                <i class="bi bi-tools me-2"></i>
                工具面板
              </h5>
            </div>
            <div class="card-body">
              <div class="mb-4">
                <h6>快速工具</h6>
                <div class="d-grid gap-2">
                  <button class="btn btn-outline-primary btn-sm" @click="useTool('badcase-analysis')">
                    <i class="bi bi-bug me-1"></i>
                    BadCase分析
                  </button>
                  <button class="btn btn-outline-success btn-sm" @click="useTool('solution-suggestion')">
                    <i class="bi bi-lightbulb me-1"></i>
                    解决方案建议
                  </button>
                  <button class="btn btn-outline-info btn-sm" @click="useTool('code-review')">
                    <i class="bi bi-code-slash me-1"></i>
                    代码审查
                  </button>
                  <button class="btn btn-outline-warning btn-sm" @click="useTool('documentation')">
                    <i class="bi bi-file-text me-1"></i>
                    文档生成
                  </button>
                </div>
              </div>
              
              <div class="mb-4">
                <h6>项目选择</h6>
                <select class="form-select mb-2" v-model="selectedProject">
                  <option value="">选择项目（可选）</option>
                  <option v-for="project in projects" :key="project.id" :value="project.id">
                    {{ project.name }}
                  </option>
                </select>
                <small class="text-muted">选择项目以获得更精准的分析</small>
              </div>
              
              <div class="mb-4">
                <h6>对话设置</h6>
                <div class="form-check">
                  <input class="form-check-input" type="checkbox" id="auto-scroll" v-model="autoScroll" checked>
                  <label class="form-check-label" for="auto-scroll">
                    自动滚动到最新消息
                  </label>
                </div>
                <div class="form-check">
                  <input class="form-check-input" type="checkbox" id="show-timestamps" v-model="showTimestamps" checked>
                  <label class="form-check-label" for="show-timestamps">
                    显示时间戳
                  </label>
                </div>
              </div>
              
              <div class="mb-4">
                <h6>操作</h6>
                <div class="d-grid gap-2">
                  <button class="btn btn-outline-secondary btn-sm" @click="clearMessages">
                    <i class="bi bi-trash me-1"></i>
                    清空对话
                  </button>
                  <button class="btn btn-outline-secondary btn-sm" @click="exportChat">
                    <i class="bi bi-download me-1"></i>
                    导出对话
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getProjects } from '../api.js'
import user, { logout } from '../store/user.js'
import TypewriterText from './TypewriterText.vue'

const router = useRouter()

// 状态
const sending = ref(false)
const autoScroll = ref(true)
const showTimestamps = ref(true)
const selectedProject = ref('')
const inputMessage = ref('')
const messageContainer = ref(null)

// 数据
const messages = ref([])
const projects = ref([])

// 消息ID计数器
let messageId = 0

// 发送消息
async function sendMessage() {
  if (!inputMessage.value.trim() || sending.value) return
  
  const userMessage = {
    id: ++messageId,
    role: 'user',
    content: inputMessage.value,
    timestamp: new Date()
  }
  
  messages.value.push(userMessage)
  const currentMessage = inputMessage.value
  inputMessage.value = ''
  
  // 滚动到底部
  if (autoScroll.value) {
    await nextTick()
    scrollToBottom()
  }
  
  // 发送到AI
  sending.value = true
  try {
    // 调用真实的后端 ReAct 接口
    const response = await fetch('http://localhost:5000/api/agent/react', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include',
      body: JSON.stringify({
        user_input: currentMessage,
        stream: true
      })
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let aiContent = '' // 收集最终响应
    let findings = [] // 收集发现的信息

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      
      const chunkText = decoder.decode(value, { stream: true })
      buffer += chunkText
      
      // 按行处理 SSE 数据
      let lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmedLine = line.trim()
        if (!trimmedLine || trimmedLine.startsWith(':')) continue
        if (!trimmedLine.startsWith('data: ')) continue
        
        try {
          const jsonStr = trimmedLine.replace('data: ', '').trim()
          if (!jsonStr || jsonStr === '[DONE]') continue
          
          const chunk = JSON.parse(jsonStr)
          
          if (chunk.type === 'stream' && chunk.payload?.lane === 'engine' && chunk.payload.data) {
            const stepEvent = chunk.payload.data
            if (stepEvent.event === 'finding' && stepEvent.data) {
              findings.push(stepEvent.data)
            }
          }
          if (chunk.type === 'bye' && chunk.payload?.findings?.length) {
            findings = [...new Set([...findings, ...chunk.payload.findings])]
          }
        } catch (e) {
          // 解析错误，继续
        }
      }
    }

    // 构建最终回复
    let finalContent = ''
    if (findings.length > 0) {
      finalContent = findings.join('\n\n')
    } else {
      finalContent = '已完成对 ' + currentMessage + ' 的分析，但未发现具体信息。'
    }

    const aiMessage = {
      id: ++messageId,
      role: 'assistant',
      content: finalContent,
      timestamp: new Date()
    }
    messages.value.push(aiMessage)
    
    if (autoScroll.value) {
      nextTick(() => scrollToBottom())
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    const errorMessage = {
      id: ++messageId,
      role: 'assistant',
      content: `错误: ${error.message || '未知错误'}`,
      timestamp: new Date()
    }
    messages.value.push(errorMessage)
  } finally {
    sending.value = false
  }
}

// 使用工具
function useTool(toolType) {
  const toolMessages = {
    'badcase-analysis': '请帮我分析这个BadCase的根本原因和可能的解决方案。',
    'solution-suggestion': '基于当前的BadCase情况，请提供一些可能的解决方案建议。',
    'code-review': '请帮我审查这段代码，找出潜在的问题和改进点。',
    'documentation': '请帮我生成相关的技术文档或说明。'
  }
  
  const message = toolMessages[toolType] || '请使用这个工具帮助我。'
  inputMessage.value = message
}

// 清空对话
function clearMessages() {
  if (confirm('确定要清空所有对话记录吗？')) {
    messages.value = []
    messageId = 0
  }
}

// 导出对话
function exportChat() {
  if (messages.value.length === 0) {
    alert('没有对话记录可导出')
    return
  }
  
  const chatContent = messages.value.map(msg => {
    const time = showTimestamps.value ? formatTime(msg.timestamp) : ''
    return `[${msg.role === 'user' ? '用户' : 'AI助手'}] ${time}\n${msg.content}\n`
  }).join('\n')
  
  const blob = new Blob([chatContent], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `chat-export-${new Date().toISOString().split('T')[0]}.txt`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// 滚动到底部
function scrollToBottom() {
  if (messageContainer.value) {
    messageContainer.value.scrollTop = messageContainer.value.scrollHeight
  }
}

// 生成AI响应（模拟）
function generateAIResponse(userMessage) {
  const responses = [
    '我理解您的问题。让我为您分析一下...',
    '这是一个很好的问题。根据我的分析...',
    '我建议您可以尝试以下方法...',
    '让我为您提供一些解决方案...',
    '基于您提供的信息，我认为...'
  ]
  
  // 简单的关键词匹配
  if (userMessage.includes('BadCase') || userMessage.includes('bug')) {
    return '我注意到您提到了BadCase相关的问题。让我帮您分析一下可能的原因和解决方案。首先，我们需要确定问题的具体表现和影响范围。'
  }
  
  if (userMessage.includes('代码') || userMessage.includes('code')) {
    return '关于代码问题，我建议您检查以下几个方面：1. 语法错误 2. 逻辑问题 3. 边界条件 4. 性能优化。您能提供具体的代码片段吗？'
  }
  
  if (userMessage.includes('解决方案') || userMessage.includes('解决')) {
    return '针对您的问题，我建议采用以下步骤：1. 问题定位 2. 原因分析 3. 方案设计 4. 实施验证 5. 效果评估。'
  }
  
  return responses[Math.floor(Math.random() * responses.length)]
}

// 获取项目列表
async function fetchProjects() {
  try {
    const response = await getProjects()
    if (response.data.success) {
      projects.value = response.data.projects
    }
  } catch (error) {
    console.error('获取项目列表失败:', error)
  }
}

// 格式化时间
function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 监听消息变化，自动滚动
watch(messages, () => {
  if (autoScroll.value) {
    nextTick(() => scrollToBottom())
  }
}, { deep: true })

// 生命周期
onMounted(() => {
  fetchProjects()
})
</script>

<style scoped>
.chat {
  min-height: 100vh;
  background-color: #f8f9fa;
}

.message-item {
  margin-bottom: 1rem;
}

.message-user {
  display: flex;
  justify-content: flex-end;
}

.message-assistant {
  display: flex;
  justify-content: flex-start;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background-color: #e9ecef;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 0.5rem;
  flex-shrink: 0;
}

.message-user .message-avatar {
  background-color: #007bff;
  color: white;
}

.message-assistant .message-avatar {
  background-color: #28a745;
  color: white;
}

.message-content {
  max-width: 70%;
}

.message-user .message-content {
  text-align: right;
}

.message-header {
  margin-bottom: 0.25rem;
}

.message-name {
  font-weight: bold;
  font-size: 0.875rem;
}

.message-time {
  color: #6c757d;
  margin-left: 0.5rem;
}

.message-text {
  background-color: #f8f9fa;
  border-radius: 0.375rem;
  padding: 0.75rem;
  word-wrap: break-word;
}

.message-text-typewriter {
  background-color: #f8f9fa;
  border-radius: 0.375rem;
  padding: 0.75rem;
  word-wrap: break-word;
  min-height: 2.5rem;
  display: flex;
  align-items: flex-start;
}

.message-user .message-text {
  background-color: #007bff;
  color: white;
}

.message-assistant .message-text {
  background-color: #e9ecef;
  color: #212529;
}

pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  margin: 0;
}
</style> 