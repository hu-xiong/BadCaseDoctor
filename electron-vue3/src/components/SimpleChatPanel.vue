<template>
  <div class="simple-chat-panel">
    <!-- 消息列表区域 -->
    <div class="messages-container" ref="messagesContainer">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="empty-icon">💬</div>
        <p>开始新的对话...</p>
      </div>
      
      <div 
        v-for="message in messages" 
        :key="message.id"
        class="message-block"
      >
        <!-- 用户消息 -->
        <div v-if="message.isUser" class="user-message-block">
          <div class="message-header">
            <span class="message-author">我</span>
            <span class="message-time">{{ message.time }}</span>
          </div>
          <div v-if="editingUserMessageId !== message.id" class="user-message-bubble" tabindex="0" @click="beginEditUserMessage(message)">
            {{ message.content }}
          </div>

          <!-- 点击用户消息后：变成与底部一致的可编辑输入框 + 控件条 -->
          <div v-else class="inline-composer">
            <div class="input-box-wrapper">
              <textarea
                ref="inlineTextareaRef"
                v-model="inlineInputMessage"
                @keydown.enter.exact="handleInlineSend"
                @keydown.enter.shift.exact="addNewLineInline"
                @keydown.esc.exact="cancelEditUserMessage"
                placeholder="输入消息... (Enter发送，Shift+Enter换行)"
                class="message-input"
                rows="1"
              ></textarea>

              <div class="input-footer">
                <div class="footer-left">
                  <div class="selector-item">
                    <select v-model="selectedAgent" class="footer-select">
                      <option value="agent">Agent</option>
                      <option value="chat">智能问答</option>
                    </select>
                  </div>
                  <div class="selector-item model-select-wrapper">
                    <img
                      v-if="isQwenModel"
                      :src="qwenIcon"
                      alt="Qwen"
                      class="model-icon"
                    />
                    <img
                      v-else-if="isErnieModel"
                      :src="ernieIcon"
                      alt="Ernie"
                      class="model-icon model-icon--ernie"
                    />
                    <img
                      v-else-if="isGlmModel"
                      :src="glmIcon"
                      alt="GLM"
                      class="model-icon"
                    />
                    <select v-model="selectedModel" @change="saveModelSelection" class="footer-select">
                      <option value="qwen3.5-plus">Qwen-3.5-Plus</option>
                      <option value="qwen-max-thinking">Qwen-Max</option>
                      <option value="ernie-4.5-turbo-128k">Ernie-4.5-Turbo</option>
                      <option value="ernie-x1-turbo-32k">Ernie-X1</option>
                      <option value="glm-4-flash">GLM-4-Flash</option>
                      <option value="glm-5">GLM-5</option>
                    </select>
                  </div>
                </div>

                <div class="footer-right">
                  <button
                    v-if="!isSending"
                    @click="handleInlineSend"
                    class="send-icon-button"
                    :disabled="!inlineInputMessage.trim()"
                    title="发送 (Enter)"
                  >
                    <img class="send-icon-img" :src="sendCursorIcon" alt="send" />
                  </button>
                  <button
                    v-else
                    @click="handleStop"
                    class="stop-icon-button"
                    title="停止生成"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <rect x="6" y="6" width="12" height="12" rx="2"></rect>
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- AI消息 -->
        <div v-else class="ai-message-block">
          <div class="message-header">
            <span class="message-author">AI</span>
            <span class="message-time">{{ message.time }}</span>
          </div>
                    
          <!-- AI等待占位（...） - 深度思考 / Todo / 结果出来前的短暂状态 -->
          <div v-if="message.understanding" class="ai-understanding">
            <div class="ai-understanding-text">
              {{ message.understanding }}
            </div>
          </div>
                    

                    
          <!-- 思考过程（文心 X1 等带推理模型）- 极简深色风格，打字机效果 -->
          <div v-if="message.reasoningContent" class="reasoning-section">
            <details class="reasoning-details">
              <summary class="reasoning-summary">
                <img class="reasoning-icon" :src="deepThinkingIcon" alt="深度思考" />
                <span class="reasoning-title">深度思考</span>
                <img
                  class="reasoning-toggle reasoning-toggle--right"
                  :src="chevronRightIcon"
                  alt="toggle-right"
                />
                <img
                  class="reasoning-toggle reasoning-toggle--down"
                  :src="chevronDownIcon"
                  alt="toggle"
                />
              </summary>
              <div class="reasoning-content">
                <div
                  class="reasoning-text reasoning-markdown"
                  v-html="formatReasoningMarkdown(message.reasoningContent)"
                ></div>
              </div>
            </details>
          </div>
          
          <!-- 待办列表 - Qoder 风格（步骤+evidence整合） -->
          <TodoTimeline 
            v-if="message.steps && message.steps.length > 0" 
            :todos="formatTodosForTimeline(message.steps, message)"
            :statusText="getTimelineStatus(message)"
          />
          
          <!-- 工具执行卡片 - 隐藏，已整合到TodoTimeline中 -->
          <!-- <ExecutionResult 
            v-if="message.executionResults && message.executionResults.length > 0" 
            :results="message.executionResults"
            :instant="message.isHistorical || false"
          /> -->
          
          <!-- 执行证据卡片 - 隐藏，已整合到TodoTimeline步骤展开中 -->
          <!-- <div v-if="message.evidences && message.evidences.length > 0" class="evidence-section">
            <div class="evidence-title">📊 执行证据</div>
            <EvidenceCard 
              v-for="(evidence, index) in message.evidences"
              :key="index"
              :evidence="evidence.data"
              :isAnimating="false"
            />
          </div> -->
          
          <!-- 搜索结果显示 -->
          <div v-if="message.searchResults && message.searchResults.length > 0" class="search-results-section">
            <div class="search-results-title">🔍 搜索结果</div>
            <div class="search-results-container">
              <div v-for="(result, index) in message.searchResults" :key="index" class="search-result-item">
                <div class="search-result-rank">{{ result.rank || index + 1 }}</div>
                <div class="search-result-content">
                  <a v-if="result.url" :href="result.url" target="_blank" class="search-result-title">{{ result.title }}</a>
                  <div v-else class="search-result-title">{{ result.title }}</div>
                  <div class="search-result-url">{{ result.url }}</div>
                  <div class="search-result-snippet">{{ result.snippet }}</div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 修改预览导航区域 - 沙箱预览：整行点击=跳转，下三角=展开/收起，无单独跳转按钮 -->
          <div v-if="message.modifyGroups && message.modifyGroups.length > 0" class="modify-navigation-section">
            <div v-for="(group, groupIdx) in message.modifyGroups" :key="groupIdx" class="collapsible-card findings-card sandbox-card" style="margin-bottom: 12px;">
              <div class="collapsible-header sandbox-header" @click="handleShowGroupInList(group, message.id)">
                <span class="card-icon">📝</span>
                <span class="card-title">沙箱预览</span>
                <span class="card-count">{{ group.items.length }} 项</span>
                <span v-if="group.plan_id" class="plan-badge">计划 #{{ group.plan_id }}</span>
                <img
                  class="sandbox-toggle"
                  :class="{ expanded: isSandboxExpanded(message.id, groupIdx) }"
                  :src="isSandboxExpanded(message.id, groupIdx) ? chevronDownIcon : chevronRightIcon"
                  alt="toggle"
                  @click.stop="toggleSandboxExpand(message.id, groupIdx)"
                />
              </div>
              <div v-show="isSandboxExpanded(message.id, groupIdx)" class="collapsible-content modify-navigation-content">
                <template v-if="group.items[0]?.diff">
                  <div v-for="(fieldDiff, idx) in group.items[0].diff" :key="idx" class="modify-field-preview">
                    <span class="field-label">{{ fieldDiff.field_label }}:</span>
                    <span :class="['old-value', { 'empty-value': !getFieldOldValue(fieldDiff) }]">
                      {{ getFieldOldValue(fieldDiff) || '未设置' }}
                    </span>
                    <span class="arrow">→</span>
                    <span class="new-value">{{ getFieldNewValue(fieldDiff) || '-' }}</span>
                  </div>
                </template>
                <div v-if="group.items.length > 1" class="group-items-hint">
                  共 {{ group.items.length }} 条连续记录待确认
                </div>
              </div>
            </div>
          </div>
          
          <!-- 兼容旧版本：单个 modifyNavigation，同样整行点击=跳转、下三角=展开 -->
          <div v-else-if="message.modifyNavigation && !message.modifyNavigation.batch_modify" class="modify-navigation-section">
            <div class="collapsible-card findings-card sandbox-card">
              <div class="collapsible-header sandbox-header" @click="handleShowModifyInList(message.modifyNavigation, message.id)">
                <span class="card-icon">📝</span>
                <span class="card-title">沙箱预览</span>
                <span class="card-count">{{ message.modifyNavigation.diff?.length || 1 }} 项</span>
                <img
                  class="sandbox-toggle"
                  :class="{ expanded: isSandboxExpanded(message.id, null) }"
                  :src="isSandboxExpanded(message.id, null) ? chevronDownIcon : chevronRightIcon"
                  alt="toggle"
                  @click.stop="toggleSandboxExpand(message.id, null)"
                />
              </div>
              <div v-show="isSandboxExpanded(message.id, null)" class="collapsible-content modify-navigation-content">
                <div v-for="(fieldDiff, idx) in (message.modifyNavigation.diff || [])" :key="idx" class="modify-field-preview">
                  <span class="field-label">{{ fieldDiff.field_label }}:</span>
                  <span :class="['old-value', { 'empty-value': !fieldDiff.lines?.find(l => l.type === 'delete')?.content }]">
                    {{ fieldDiff.lines?.find(l => l.type === 'delete')?.content || '未设置' }}
                  </span>
                  <span class="arrow">→</span>
                  <span class="new-value">{{ fieldDiff.lines?.find(l => l.type === 'add')?.content || '-' }}</span>
                </div>
              </div>
            </div>
          </div>
          
          <!-- Bug 导航区域 - 独立于 findings 之外（可折叠深色背景） -->
          <div v-if="message.navigation && message.navigation.type === 'multiple'" class="bug-navigation-section">
            <div class="collapsible-card findings-card">
              <details :open="true">
                <summary class="collapsible-header">
                  <span class="card-icon">🐛</span>
                  <span class="card-title">点击跳转到 Bug</span>
                  <span class="card-count">{{ message.navigation.items.length }} 条</span>
                  <span class="card-arrow">▼</span>
                </summary>
                <div class="collapsible-content bug-navigation-list">
                  <div
                    v-for="(item, idx) in message.navigation.items"
                    :key="idx"
                    class="bug-nav-item"
                    @click="handleNavigation(item)"
                  >
                    <span class="bug-nav-icon">➤</span>
                    <span class="bug-nav-title">{{ item.bug_title }}</span>
                    <span v-if="item.plan_name" class="bug-nav-plan">{{ item.plan_name }}</span>
                  </div>
                </div>
              </details>
            </div>
          </div>
                    
          <!-- 最终回复（无统一总结时展示） -->
          <div v-if="message.finalResponse && !hasUnifiedSummary(message)" class="ai-response">
            <div class="ai-response-text">
              {{ message.finalResponse }}
            </div>
          </div>
          
          <!-- 统一总结：放在最后，Cursor 式「思考 Xs」+ 打字机（思考秒数，非总耗时） -->
          <div v-if="hasUnifiedSummary(message)" class="unified-summary-section">
            <div class="unified-summary-header">总结 {{ (message.agentResult.thinking_time ?? message.agentResult.execution_time ?? 0).toFixed(2) }}s</div>
            <div class="unified-summary-content reasoning-content">
              <div class="reasoning-text unified-summary-text">{{ getUnifiedSummaryBody(message) }}</div>
              <CreatePreview 
                v-if="message.createPreview && message.createPreview.preview" 
                :previewData="message.createPreview"
                @confirm="handleConfirmCreate"
                @cancel="handleCancelCreate"
              />
            </div>
          </div>
                    
          <!-- Bug 保存按钮（仅当有 Bug 结果时显示） -->
          <div v-if="message.agentResult && message.agentResult.bugs_found && message.agentResult.bugs_found.length > 0" class="save-bugs-section">
            <button @click="handleSaveBugs(message.agentResult)" class="save-bugs-button">
              💾 保存 {{ message.agentResult.bugs_found.length }} 个 Bug
            </button>
            <span class="bugs-count">发现 {{ message.agentResult.bugs_found.length }} 个问题</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 输入区域 -->
    <div class="input-container">
      <div class="input-box-wrapper">
        <textarea 
          ref="textareaRef"
          v-model="inputMessage"
          @input="autoResize"
          @keydown.enter.exact="handleSend"
          @keydown.enter.shift.exact="addNewLine"          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          placeholder="输入消息... (Enter发送，Shift+Enter换行)"
          class="message-input"
          rows="1"
        ></textarea>
        
        <div class="input-footer">
          <div class="footer-left">
            <div class="selector-item">
              <select v-model="selectedAgent" class="footer-select">
                <option value="agent">Agent</option>
                <option value="chat">智能问答</option>
              </select>
            </div>
            <!-- 移除 ReAct/执行选择器 - 统一使用 ReAct 模式 -->
          <div class="selector-item model-select-wrapper">
            <img
              v-if="isQwenModel"
              :src="qwenIcon"
              alt="Qwen"
              class="model-icon"
            />
            <img
              v-else-if="isErnieModel"
              :src="ernieIcon"
              alt="Ernie"
              class="model-icon model-icon--ernie"
            />
            <img
              v-else-if="isGlmModel"
              :src="glmIcon"
              alt="GLM"
              class="model-icon"
            />
            <select v-model="selectedModel" @change="saveModelSelection" class="footer-select">
              <option value="qwen3.5-plus">Qwen-3.5-Plus</option>
              <option value="qwen-max-thinking">Qwen-Max</option>
              <option value="ernie-4.5-turbo-128k">Ernie-4.5-Turbo</option>
              <option value="ernie-x1-turbo-32k">Ernie-X1</option>
              <option value="glm-4-flash">GLM-4-Flash</option>
              <option value="glm-5">GLM-5</option>
            </select>
          </div>
          </div>
          <div class="footer-right">
            <button 
              v-if="!isSending"
              @click="handleSend" 
              class="send-icon-button"
              :disabled="!inputMessage.trim()"
              title="发送 (Enter)"
            >
              <img class="send-icon-img" :src="sendCursorIcon" alt="send" />
            </button>
            <button 
              v-else
              @click="handleStop" 
              class="stop-icon-button"
              title="停止生成"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <rect x="6" y="6" width="12" height="12" rx="2"></rect>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, onUnmounted, watch, computed } from 'vue'
import { marked } from 'marked'
import { BACKEND_BASE_URL, getChatSession, addChatMessage, saveAgentBugs, generateSessionTitle } from '../api.js'
import EvidenceCard from './EvidenceCard.vue'
import StepTimeline from './StepTimeline.vue'
import StreamingMessage from './StreamingMessage.vue'
import TodoTimeline from './TodoTimeline.vue'
import ExecutionResult from './ExecutionResult.vue'
import CreatePreview from './CreatePreview.vue'
import deepThinkingIcon from '../assets/deep-thinking-icon.svg'
import chevronRightIcon from '../assets/chevron-right-qoder.png'
import chevronDownIcon from '../assets/chevron-down-qoder.png'
import qwenIcon from '../assets/qwen-icon.png'
import ernieIcon from '../assets/ernie-icon.png'
import glmIcon from '../assets/glm-icon.png'
import sendCursorIcon from '../assets/send-cursor.png'

// Props
const props = defineProps({
  sessionId: {
    type: Number,
    required: false,
    default: null
  },
  projectId: {
    type: Number,
    required: false,
    default: null
  }
})

const emit = defineEmits(['title-updated'])

  const messages = ref([])

  // 详情字段列表（不在列表中显示的字段，用于沙箱预览分组）
  const DETAIL_FIELDS = [
    'base_problem',
    'reproduction_steps',
    'answer',
    'correct_answer',
    'badcase_result',
    'solution',
    'problem_reason',
    'description',
    'steps_to_reproduce',
    'expected_result',
    'actual_result',
    'preconditions',
    'steps',
    'remark',
    'baseline',
    'reproduce_steps'
  ]

const inputMessage = ref('')
const editingUserMessageId = ref(null)
const inlineInputMessage = ref('')
const inlineTextareaRef = ref(null)

const handleDocumentPointerDown = (e) => {
  // 处于内联编辑态时：点到编辑区外面 -> 自动退出恢复原样
  if (!editingUserMessageId.value) return
  const target = e?.target
  if (!target) return
  // 点击在内联编辑器内部则不处理
  if (target.closest && target.closest('.inline-composer')) return
  cancelEditUserMessage()
}
const selectedAgent = ref('agent')
// 从 localStorage 读取上次选择的模型，如果没有则使用默认值
const savedModel = localStorage.getItem('selectedChatModel')
const selectedModel = ref(savedModel || 'ernie-4.5-turbo-128k')  // 默认文心；可选 qwen3.5-plus / ernie-4.5-turbo-128k / glm-5
const isQwenModel = computed(() => selectedModel.value && selectedModel.value.startsWith('qwen'))
const isErnieModel = computed(() => selectedModel.value && selectedModel.value.startsWith('ernie'))
const isGlmModel = computed(() => selectedModel.value && selectedModel.value.startsWith('glm'))
const messagesContainer = ref(null)
const textareaRef = ref(null)
const isSending = ref(false)
const isComposing = ref(false)  // 输入法组合状态
const abortController = ref(null)  // 用于终止请求
const currentProjectId = ref(null)
// 沙箱预览展开状态：key = `${messageId}-${groupIdx}` 或 `${messageId}-single`，点击下三角切换
const sandboxExpanded = ref({})
const getSandboxKey = (messageId, groupIdx) => (groupIdx == null ? `${messageId}-single` : `${messageId}-${groupIdx}`)
const isSandboxExpanded = (messageId, groupIdx) => sandboxExpanded.value[getSandboxKey(messageId, groupIdx)] !== false
const toggleSandboxExpand = (messageId, groupIdx) => {
  const key = getSandboxKey(messageId, groupIdx)
  sandboxExpanded.value = { ...sandboxExpanded.value, [key]: sandboxExpanded.value[key] === false }
}


// 将运行中状态收敛（停止/异常时用）
const finalizeRunningMessage = (aiMessage, reason = 'stopped') => {
  if (!aiMessage) return

  if (Array.isArray(aiMessage.steps)) {
    aiMessage.steps.forEach(step => {
      if (step?.status === 'running') {
        step.status = 'skipped'
        step.description = reason === 'stopped' ? '已停止' : '已中断'
        if (step.toolCall && step.toolCall.output === '执行中...') {
          step.toolCall.output = reason === 'stopped' ? '已停止' : '已中断'
        }
      }
    })
  }

  if (aiMessage.agentResult) {
    aiMessage.agentResult.status = reason === 'stopped' ? 'cancelled' : 'failed'
  }

  // 顶部提示同步更新，避免还停留在“修改中/执行中”
  if (typeof aiMessage.understanding === 'string') {
    aiMessage.understanding = reason === 'stopped' ? '⏹ 已停止生成' : '⚠️ 已中断'
  }

  if (!aiMessage.finalResponse) {
    aiMessage.finalResponse = reason === 'stopped' ? '已停止生成' : '已中断'
  }
}

// 格式化消息内容（支持简单的markdown）
const formatMessage = (content) => {
  return content
    .replace(/\n/g, '<br>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

// 思考过程：使用 marked 做完整 Markdown 渲染（换行、加粗、列表、代码块等）
marked.setOptions({ gfm: true, breaks: true })
const formatReasoningMarkdown = (content) => {
  if (!content || typeof content !== 'string') return ''
  try {
    let text = content.trim()
    // 若模型未输出换行，在中文句号/分号后插入换行，便于展示段落
    if (!/\n/.test(text) && /[。；]/.test(text)) {
      text = text.replace(/([。；])/g, '$1\n')
    }
    return marked.parse(text, { gfm: true, breaks: true })
  } catch (e) {
    return content.replace(/\n/g, '<br>')
  }
}

// 获取工具层级
const getToolLevel = (toolName) => {
  if (!toolName) return 'level-unknown'
  const name = toolName.toLowerCase()
  if (name.startsWith('l1_') || name.includes('click') || name.includes('input') || name.includes('wait') || name.includes('assert')) {
    return 'level-l1'
  } else if (name.startsWith('l2_') || name.includes('form_') || name.includes('fill') || name.includes('submit')) {
    return 'level-l2'
  } else if (name.startsWith('l3_') || name.includes('complete_') || name.includes('test_')) {
    return 'level-l3'
  }
  return 'level-unknown'
}

// 获取工具图标
const getToolIcon = (toolName) => {
  if (!toolName) return '🔧'
  const name = toolName.toLowerCase()
  if (name.includes('click')) return '🖱️'
  if (name.includes('input') || name.includes('text')) return '⌨️'
  if (name.includes('wait')) return '⏳'
  if (name.includes('assert') || name.includes('check')) return '✓'
  if (name.includes('form')) return '📋'
  if (name.includes('submit')) return '📤'
  if (name.includes('login') || name.includes('complete')) return '🔑'
  if (name.includes('test') || name.includes('scenario')) return '🧪'
  return '🔧'
}

// 获取工具层级标签
const getToolLevelLabel = (toolName) => {
  const level = getToolLevel(toolName)
  if (level === 'level-l1') return '(L1 原子)'
  if (level === 'level-l2') return '(L2 复合)'
  if (level === 'level-l3') return '(L3 流程)'
  return ''
}

// 将对象转换为人类可读的摘要
const formatObjectToSummary = (obj) => {
  if (!obj || typeof obj !== 'object') return ''
  
  // 处理plan_tree结构
  if (obj.plan_tree) {
    const planCount = obj.plan_tree.total_plans || 0
    const rootCount = obj.plan_tree.root_plans?.length || 0
    return `📋 解析计划树：共 ${planCount} 个计划，${rootCount} 个根计划`
  }
  
  // 处理badcase_analysis
  if (obj.badcase_analysis && Array.isArray(obj.badcase_analysis)) {
    const count = obj.badcase_analysis.length
    const keywords = obj.badcase_analysis[0]?.extracted_keywords?.join(', ') || ''
    return `🔍 定位 ${count} 条BadCase${keywords ? `（关键词：${keywords}）` : ''}`
  }
  
  // 处理bug_location
  if (obj.bug_location && Array.isArray(obj.bug_location)) {
    const count = obj.bug_location.length
    return `🐛 定位Bug：${count} 条`
  }
  
  // 处理plan_attribution
  if (obj.plan_attribution && Array.isArray(obj.plan_attribution)) {
    const count = obj.plan_attribution.length
    return `🎯 计划归属分析：${count} 条建议`
  }
  
  // 处理comparison_report
  if (obj.comparison_report) {
    return `📊 生成对比报告`
  }
  
  // 处理bugs查询结果
  if (obj.bugs && Array.isArray(obj.bugs)) {
    const count = obj.bugs.length
    const priorities = obj.bugs.reduce((acc, bug) => {
      acc[bug.priority] = (acc[bug.priority] || 0) + 1
      return acc
    }, {})
    const priorityStr = Object.entries(priorities)
      .map(([p, c]) => `${p}优先级${c}条`)
      .join('、')
    return `🐛 查询到 ${count} 个Bug（${priorityStr}）`
  }
  
  // 处理summary
  if (obj.summary && typeof obj.summary === 'string') {
    return obj.summary
  }
  
  // 默认返回简要信息
  const keys = Object.keys(obj)
  if (keys.length > 0) {
    return `📝 包含字段：${keys.slice(0, 3).join('、')}${keys.length > 3 ? '等' : ''}`
  }
  
  return ''
}

// 格式化 steps 为 TodoTimeline 所需的 todos 数据结构
const formatTodosForTimeline = (steps, message) => {
  if (!steps || !Array.isArray(steps)) return []
  
  return steps.map((step, index) => {
    // 提取工具名称
    let toolName = step.toolCall?.name || step.title || extractToolName(step.originalTodo || step.title)
    
    // 生成友好的步骤描述（参考图2风格：简洁直接）
    let friendlyText = ''
    let resultSummary = ''
    
    // 判断步骤是否已完成
    const isCompleted = step.status === 'completed' || step.status === 'done'
    const isSkipped = step.status === 'skipped'
    const isRunning = step.status === 'running'
    
    // 优先使用步骤标题（已经是工具名称）
    if (step.title && ['database_query', 'grep', 'modify', 'create', 'browser_test', 'search'].includes(step.title)) {
      toolName = step.title
    }
    
    if (toolName === 'database_query') {
      friendlyText = '🔍 使用 database_query 工具查询数据库'
      // 只有完成时才显示结果摘要
      if (isSkipped) {
        resultSummary = '已跳过'
      } else if (isCompleted && step.toolCall?.output) {
        const output = step.toolCall.output
        try {
          const data = typeof output === 'string' ? JSON.parse(output) : output
          if (data.bugs && Array.isArray(data.bugs)) {
            resultSummary = `查询完成，找到 ${data.bugs.length} 个Bug`
          } else if (data.similar_count !== undefined) {
            resultSummary = `查询完成，相似缺陷: ${data.similar_count} 条`
          } else if (data.data?.bugs) {
            resultSummary = `查询完成，找到 ${data.data.bugs.length} 个Bug`
          } else {
            resultSummary = '查询完成'
          }
        } catch {
          resultSummary = '查询完成'
        }
      } else if (isRunning) {
        resultSummary = '查询中...'
      }
    } else if (toolName === 'grep') {
      friendlyText = '🎯 使用 grep 工具进行精准定位分析'
      // 只有完成时才显示结果摘要
      if (isSkipped) {
        resultSummary = '已跳过'
      } else if (isCompleted) {
        const output = step.toolCall?.output
        if (output) {
          try {
            const data = typeof output === 'string' ? JSON.parse(output) : output
            // 优先使用后端生成的summary（已包含计划名和意图分析）
            if (data.data?.summary) {
              resultSummary = data.data.summary
            } else if (data.data?.badcase_analysis) {
              const count = data.data.badcase_analysis.length || 0
              resultSummary = count > 0 ? `分析完成，定位 ${count} 条BadCase` : '分析完成，未找到BadCase'
            } else if (data.data?.plan_tree) {
              const planCount = data.data.plan_tree.total_plans || 0
              const badcaseCount = data.data.badcase_analysis?.length || 0
              resultSummary = badcaseCount > 0 
                ? `分析完成，解析 ${planCount} 个计划，定位 ${badcaseCount} 条BadCase`
                : `分析完成，解析 ${planCount} 个计划，未找到BadCase`
            } else {
              resultSummary = '分析完成，未找到匹配项'
            }
          } catch {
            resultSummary = '分析完成'
          }
        } else {
          // 没有输出时也显示结果
          resultSummary = '分析完成，无结果返回'
        }
      } else if (isRunning) {
        resultSummary = '分析中...'
      }
    } else if (toolName === 'browser_test') {
      friendlyText = '🌐 使用 browser_test 工具执行浏览器自动化测试'
      resultSummary = isSkipped ? '已跳过' : (isCompleted ? '测试执行完成' : (isRunning ? '测试执行中...' : ''))
    } else if (toolName === 'log_analyzer') {
      friendlyText = '📋 使用 log_analyzer 工具分析日志'
      resultSummary = isSkipped ? '已跳过' : (isCompleted ? '日志分析完成' : (isRunning ? '日志分析中...' : ''))
    } else if (toolName === 'modify') {
      friendlyText = '✏️ 使用 modify 工具修改数据'
      if (isSkipped) {
        resultSummary = '已跳过'
      } else if (isCompleted) {
        const output = step.toolCall?.output
        if (output) {
          try {
            const data = typeof output === 'string' ? JSON.parse(output) : output
            if (data.batch_modify && data.results) {
              const successCount = data.results.filter(r => r.result?.success).length
              resultSummary = `批量修改完成，成功 ${successCount}/${data.results.length} 条`
            } else if (data.success && data.diff) {
              resultSummary = '修改预览完成，等待确认'
            } else if (data.success) {
              resultSummary = '修改执行成功'
            } else if (data.error) {
              resultSummary = `修改失败: ${data.error}`
            } else {
              resultSummary = '修改完成'
            }
          } catch {
            resultSummary = '修改完成'
          }
        } else {
          resultSummary = '修改完成，无结果返回'
        }
      } else if (isRunning) {
        // 实时显示后端下发的进度文案（流式）
        resultSummary = step.description || '修改中...'
      }
    } else {
      // 其他工具，使用原始title
      friendlyText = step.title || step.description || '未知任务'
      resultSummary = isSkipped ? '已跳过' : (isCompleted ? '执行完成' : (isRunning ? '执行中...' : ''))
    }
    
    // 关联对应的evidence卡片
    const relatedEvidence = message?.evidences?.find(ev => 
      ev.data?.tool === toolName || ev.data?.title?.includes(toolName)
    )
    
    return {
      text: friendlyText,
      resultSummary: resultSummary,  // 结果摘要（modify 运行中时为最新进度）
      status: step.status || 'pending',
      showTypewriter: step.status === 'running',
      toolCall: step.toolCall,  // 保留toolCall供展开
      evidence: relatedEvidence?.data,  // 关联的evidence数据
      progressLog: step.progressLog || []  // modify 等实时进度日志，用于流式多行展示
    }
  })
}

// 从标题中提取工具名称
const extractToolName = (title) => {
  if (!title) return ''
  if (title.includes('database_query')) return 'database_query'
  if (title.includes('grep')) return 'grep'
  if (title.includes('modify')) return 'modify'
  if (title.includes('create')) return 'create'
  if (title.includes('browser_test')) return 'browser_test'
  if (title.includes('log_analyzer')) return 'log_analyzer'
  if (title.includes('search')) return 'search'
  return ''
}

// 获取 diff 字段的旧值（兼容 delete 和 unchanged 类型）
const getFieldOldValue = (fieldDiff) => {
  if (!fieldDiff || !fieldDiff.lines) return null
  // 优先找 delete 类型
  const deleteLine = fieldDiff.lines.find(l => l.type === 'delete')
  if (deleteLine) return deleteLine.content
  // 如果只有 unchanged，说明值没变，返回该值作为旧值
  const unchangedLine = fieldDiff.lines.find(l => l.type === 'unchanged')
  if (unchangedLine) return unchangedLine.content
  return null
}

// 获取 diff 字段的新值（兼容 add 和 unchanged 类型）
const getFieldNewValue = (fieldDiff) => {
  if (!fieldDiff || !fieldDiff.lines) return null
  // 优先找 add 类型
  const addLine = fieldDiff.lines.find(l => l.type === 'add')
  if (addLine) return addLine.content
  // 如果只有 unchanged，说明值没变，返回该值作为新值
  const unchangedLine = fieldDiff.lines.find(l => l.type === 'unchanged')
  if (unchangedLine) return unchangedLine.content
  return null
}

// 获取时间轴状态描述
const getTimelineStatus = (message) => {
  const hasRunning = message.steps?.some(s => s.status === 'running')
  const allCompleted = message.steps?.every(s => s.status === 'completed')
  
  if (hasRunning) {
    return '正在规划任务步骤...'
  } else if (allCompleted) {
    return ''
  } else {
    return '正在规划任务步骤...'
  }
}

// 判断是否有运行中的步骤
const hasRunningSteps = (message) => {
  return message.steps?.some(s => s.status === 'running') || false
}

// 是否显示「统一总结」块（关键发现 + 执行统计合并，Cursor 式耗时 Xs）
const hasUnifiedSummary = (message) => {
  const r = message.agentResult
  if (!r || r.status !== 'success') return false
  return (r.findings && r.findings.length > 0) || r.execution_time != null || (r.steps_count != null && r.steps_count > 0)
}

// 统一总结正文：优先使用后端大模型生成的 summaryText（Cursor 式一段话），否则回退为 findings + 执行统计
const getUnifiedSummaryBody = (message) => {
  const r = message.agentResult
  if (r?.summaryText && typeof r.summaryText === 'string' && r.summaryText.trim()) {
    return r.summaryText.trim()
  }
  const lines = []
  if (r?.findings && r.findings.length > 0) {
    r.findings.forEach(f => lines.push('• ' + (typeof f === 'string' ? f : String(f))))
  }
  const stepsCount = r?.steps_count ?? message.steps?.length ?? 0
  const duration = Number(r?.execution_time ?? 0)
  if (stepsCount > 0 || duration > 0) {
    if (lines.length) lines.push('')
    lines.push(`完成步骤: ${stepsCount} 个`)
    lines.push(`耗时: ${duration.toFixed(2)}s`)
    lines.push('任务执行成功')
  }
  const body = lines.join('\n')
  // 有思考耗时但无思考内容时提示（qwen-max 等模型可能不返回 reasoning_content）
  const thinkingTime = (r?.thinking_time ?? r?.execution_time ?? 0)
  if (thinkingTime > 0 && !(message.reasoningContent && message.reasoningContent.trim())) {
    const hint = '思考过程未返回（当前模型或接口可能不返回思考内容）。'
    return body ? `${hint}\n\n${body}` : hint
  }
  return body
}

// 处理导航指令（展开计划并定位Bug）
const handleNavigation = (navigation) => {
  if (!navigation) return
  
  // 处理多个Bug导航：不自动跳转，由用户点击选择
  if (navigation.type === 'multiple') {
    console.log('[NAV] 检测到多个Bug，在关键发现中显示列表，等待用户点击')
    return
  }
  
  // 单个Bug导航：直接跳转
  if (navigation.type !== 'expand_and_locate') return
  
  console.log('[NAV] 执行导航:', navigation)
  
  // 发送自定义事件给父组件ProjectDetail
  const event = new CustomEvent('grep-navigate', {
    detail: {
      planId: navigation.plan_id,
      bugId: navigation.bug_id,
      target: navigation.target
    }
  })
  window.dispatchEvent(event)
  
  console.log('[NAV] 已发送导航事件，detail:', event.detail)
}

// 确认修改
const handleConfirmModify = async (modifyData) => {
  console.log('[MODIFY] 用户确认修改:', modifyData)
  
  // 清除modifyNavigation
  const currentMessage = messages.value[messages.value.length - 1]
  if (currentMessage) {
    currentMessage.modifyNavigation = null
  }
  
  // 调用modify工具，confirm=true
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_input: `确认修改${modifyData.target} ID=${modifyData.target_id}`,
        project_id: props.projectId,
        model: selectedModel.value,
        session_id: props.sessionId,
        confirm_modify: modifyData  // 传递modify数据
      })
    })
    
    console.log('[MODIFY] 修改已提交')
  } catch (error) {
    console.error('[MODIFY] 修改失败:', error)
  }
}

// 沙箱预览按钮文案：按目标类型显示「跳转到Bug/BadCase/测试用例详情」
const getModifyJumpButtonLabel = (target) => {
  if (target === 'bug') return '跳转到Bug详情'
  if (target === 'badcase') return '跳转到BadCase详情'
  if (target === 'testcase') return '跳转到测试用例详情'
  return '在列表中显示'
}

// 在列表中显示修改（并跳转到对应详情页）
// 处理分组跳转到列表
const handleShowGroupInList = (group, messageId) => {
  console.log('[MODIFY] 分组跳转到列表:', group, 'messageId:', messageId)
  
  // 防御性检查
  if (!group) {
    console.error('[MODIFY] group 为空')
    return
  }
  if (!group.items || !Array.isArray(group.items) || group.items.length === 0) {
    console.warn('[MODIFY] group.items 为空或无效')
    return
  }
  
  // 为该组的每个记录发送事件
  group.items.forEach((item, index) => {
    // 防御性检查
    const rawId = item?.target_id ?? item?.targetId ?? item?.id
    if (!item || rawId === undefined || rawId === null) {
      console.warn('[MODIFY] 跳过无效 item:', item)
      return
    }
    
    const intTargetId = parseInt(rawId)
    if (isNaN(intTargetId)) {
      console.warn('[MODIFY] 跳过无效 target_id:', rawId)
      return
    }
    
    // 只有 confirmation_required === false 才表示已处理（不需要确认）
    // success: true 只表示预览成功，不表示已执行
    const alreadyProcessed = item.confirmation_required === false
    
    console.log('[MODIFY] 发送事件:', {
      targetId: intTargetId,
      confirmation_required: item.confirmation_required,
      alreadyProcessed,
      diff: item.diff
    })
    
    const event = new CustomEvent('show-modify-in-list', {
      detail: {
        targetId: intTargetId,
        target: item.target || 'badcase',
        diff: item.diff || [],
        modifications: item.modifications || {},
        plan_id: group.plan_id,  // 使用分组的 plan_id
        executed: alreadyProcessed,
        messageId: messageId,
        batchIndex: index
      },
      bubbles: true
    })
    window.dispatchEvent(event)
    console.log('[DEBUG-show-modify-in-list from SimpleChatPanel]', JSON.stringify(event.detail, null, 2))
  })
}

const handleShowModifyInList = (modifyData, messageId) => {
  console.log('[MODIFY] 在列表中显示修改(来自后端结果):', modifyData, 'messageId:', messageId)
  
  // 防御性检查
  if (!modifyData) {
    console.error('[MODIFY] modifyData 为空')
    return
  }  
  
  // 批量修改：为每个记录发送单独的事件
  if (modifyData.batch_modify && modifyData.batch_results && Array.isArray(modifyData.batch_results) && modifyData.batch_results.length > 0) {
    console.log('[MODIFY] 批量修改，发送多个事件')
    modifyData.batch_results.forEach((result, index) => {
      // 防御性检查
      if (!result || result.target_id === undefined) {
        console.warn('[MODIFY] 跳过无效 result:', result)
        return
      }
      
      const intTargetId = parseInt(result.target_id)
      if (isNaN(intTargetId)) {
        console.warn('[MODIFY] 跳过无效 target_id:', result.target_id)
        return
      }
      
      // 对于预览结果：success 只表示“预览成功”，不代表已经执行修改
      // 只有 confirmation_required === false 才表示修改已真正应用
      const alreadyProcessed = result.confirmation_required === false
      console.log('[MODIFY] 发送批量 show-modify-in-list 事件:', {
        intTargetId,
        target: result.target || 'badcase',
        executed: alreadyProcessed
      })
      
      const event = new CustomEvent('show-modify-in-list', {
        detail: {
          targetId: intTargetId,
          target: result.target || 'badcase',
          diff: result.diff || [],
          modifications: result.modifications || {},
          executed: alreadyProcessed,
          messageId: messageId,
          batchIndex: index
        },
        bubbles: true
      })
      window.dispatchEvent(event)
    })
    return
  }
  
  // 单个修改
  const rawId = modifyData.target_id ?? modifyData.targetId ?? modifyData.id
  const intTargetId = parseInt(rawId)
  if (isNaN(intTargetId)) {
    console.error('[MODIFY] 无效的 target_id:', rawId)
    return
  }
  
  // 对于单条修改：success 只表示预览或检查成功，不代表已经落库
  const alreadyProcessed = modifyData.cancelled === true || 
                          modifyData.confirmation_required === false
  console.log('[MODIFY] 发送单条 show-modify-in-list 事件:', {
    intTargetId,
    target: modifyData.target || 'badcase',
    executed: alreadyProcessed
  })
  
  const event = new CustomEvent('show-modify-in-list', {
    detail: {
      targetId: intTargetId,
      target: modifyData.target || 'badcase',
      diff: modifyData.diff || [],
      modifications: modifyData.modifications || {},
      plan_id: modifyData.plan_id || modifyData.before?.plan_id || null,
      executed: alreadyProcessed,
      messageId: messageId
    },
    bubbles: true
  })
  window.dispatchEvent(event)
}

// 取消修改
const handleCancelModify = () => {
  console.log('[MODIFY] 用户取消修改')
  // 清除modifyNavigation
  const currentMessage = messages.value[messages.value.length - 1]
  if (currentMessage) {
    currentMessage.modifyNavigation = null
  }
}

// 确认应用沙箱预览的修改（已废弃，现在统一跳转到左侧列表确认）
const handleConfirmModification = async (modifyData) => {
  console.log('[MODIFY] 此方法已废弃，请使用 handleShowModifyInList')
}

// 取消沙箱预览的修改
const handleCancelModification = (message) => {
  console.log('[MODIFY] 用户取消沙箱预览')
  message.modifyNavigation = null
}

// 审核单个修改项 - 采纳
const handleApproveItem = async (item) => {
  console.log('[MODIFY] 用户采纳单项修改:', item)
  // 修改已经执行，这里只是记录用户确认
  // 可以发送通知或更新UI状态
}

// 审核单个修改项 - 拒绝
const handleRejectItem = async (item) => {
  console.log('[MODIFY] 用户拒绝单项修改:', item)
  // 需要回滚该修改
  if (item.result?.before) {
    try {
      const response = await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_input: `回滚修改，恢复原状态`,
          project_id: props.projectId,
          model: selectedModel.value,
          session_id: props.sessionId,
          rollback_modify: {
            target: 'bug',
            target_id: item.bug_id,
            modifications: item.result.before
          }
        })
      })
      console.log('[MODIFY] 回滚请求已发送')
    } catch (error) {
      console.error('[MODIFY] 回滚失败:', error)
    }
  }
}

// 全部采纳
const handleApproveAll = async (results) => {
  console.log('[MODIFY] 用户采纳全部修改:', results)
  // 所有修改已执行，记录确认
}

// 全部拒绝
const handleRejectAll = async (results) => {
  console.log('[MODIFY] 用户拒绝全部修改:', results)
  // 需要回滚所有修改
  for (const item of results) {
    if (item.result?.before) {
      try {
        await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_input: `回滚修改`,
            project_id: props.projectId,
            model: selectedModel.value,
            session_id: props.sessionId,
            rollback_modify: {
              target: 'bug',
              target_id: item.bug_id,
              modifications: item.result.before
            }
          })
        })
      } catch (error) {
        console.error('[MODIFY] 回滚失败:', error)
      }
    }
  }
}

// 确认创建
const handleConfirmCreate = async (createData) => {
  console.log('[CREATE] 用户确认创建:', createData)
  
  // 调用create工具，confirm=true
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/devops/chat_stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_input: `确认创建${createData.target}`,
        project_id: props.projectId,
        model: selectedModel.value,
        session_id: props.sessionId,
        confirm_create: createData  // 传递create数据
      })
    })
    
    console.log('[CREATE] 创建已提交')
  } catch (error) {
    console.error('[CREATE] 创建失败:', error)
  }
}

// 取消创建
const handleCancelCreate = () => {
  console.log('[CREATE] 用户取消创建')
  // 只需记录日志，不做处理
}

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 加载会话消息
const loadSessionMessages = async () => {
  if (!props.sessionId) {
    console.log('[SimpleChatPanel] sessionId为null，跳过加载')
    return
  }
  
  console.log('[SimpleChatPanel] 开始加载会话sessionId:', props.sessionId)
  
  try {
    const response = await getChatSession(props.sessionId)
    console.log('[SimpleChatPanel] 会话响应:', response.data)
    if (response.data.success) {
      // 转换数据库消息到组件格式
      messages.value = response.data.session.messages.map(msg => {
        if (msg.is_user) {
          return {
            id: msg.id,
            isUser: true,
            content: msg.content,
            time: new Date(msg.created_at).toLocaleTimeString(),
            isHistorical: true  // 标记为历史消息
          }
        } else {
          const modifyNav = msg.modify_navigation ? JSON.parse(msg.modify_navigation) : null
          const modifyGroups = msg.modify_groups ? JSON.parse(msg.modify_groups) : null
          
          // 检查历史消息中的 modifyNavigation 是否已执行
          // 如果 confirmation_required=true 但数据库中的记录已被修改，标记为已执行
          // 这里先保留原始状态，后续通过API检查
          
          return {
            id: msg.id,
            isUser: false,
            understanding: msg.understanding,
            reasoningContent: msg.reasoning,  // 历史消息的思考过程
            steps: msg.steps ? JSON.parse(msg.steps) : [],
            executionResults: msg.execution_results ? JSON.parse(msg.execution_results) : [],
            agentResult: msg.agent_result ? JSON.parse(msg.agent_result) : { findings: [], recommendations: [], status: 'success' },
            evidences: msg.evidences ? JSON.parse(msg.evidences) : [],
            navigation: msg.navigation ? JSON.parse(msg.navigation) : null,
            modifyNavigation: modifyNav,  // 加载 modifyNavigation
            modifyGroups: modifyGroups,  // 加载 modifyGroups
            finalResponse: msg.final_response,
            time: new Date(msg.created_at).toLocaleTimeString(),
            isHistorical: true  // 标记为历史消息
          }
        }
      })
      
      // 检查历史 modifyNavigation 的执行状态
      checkModifyNavigationStatus()
      
      scrollToBottom()
    }
  } catch (error) {
    console.error('加载会话消息失败:', error)
  }
}

// 保存模型选择到 localStorage
const saveModelSelection = () => {
  localStorage.setItem('selectedChatModel', selectedModel.value)
  console.log('[MODEL] 已保存模型选择:', selectedModel.value)
}

// 切换思考过程的展开/收起状态
const toggleReasoning = (message) => {
  message.showReasoning = !message.showReasoning
}

// 检查历史 modifyNavigation 的执行状态
const checkModifyNavigationStatus = async () => {
  // 遍历所有消息，检查 modifyNavigation 和 modifyGroups 是否需要验证执行状态
  for (const msg of messages.value) {
    // 检查 modifyGroups（批量修改分组）
    if (msg.modifyGroups && Array.isArray(msg.modifyGroups) && msg.modifyGroups.length > 0) {
      for (const group of msg.modifyGroups) {
        if (!group.items || !Array.isArray(group.items)) continue
        
        for (const item of group.items) {
          // 只检查需要确认且未标记为成功的项
          if (item.confirmation_required !== false && !item.success) {
            const { target, target_id, modifications } = item
            
            if (!target || !target_id || !modifications) continue
            
            try {
              const isApplied = await checkRecordModified(target, target_id, modifications)
              if (isApplied) {
                item.confirmation_required = false
                item.success = true
                console.log('[MODIFY] 历史消息 modifyGroups 检测到修改已生效:', target_id)
              }
            } catch (error) {
              console.error('[MODIFY] 检查 modifyGroups 执行状态失败:', error)
            }
          }
        }
      }
    }
    
    // 检查单个 modifyNavigation
    if (msg.modifyNavigation && msg.modifyNavigation.confirmation_required && !msg.modifyNavigation.success) {
      const { target, target_id, modifications } = msg.modifyNavigation
      
      if (!target || !target_id || !modifications) continue
      
      try {
        const isApplied = await checkRecordModified(target, target_id, modifications)
        if (isApplied) {
          msg.modifyNavigation.success = true
          msg.modifyNavigation.confirmation_required = false
          console.log('[MODIFY] 历史消息 modifyNavigation 检测到修改已生效:', msg.id)
        }
      } catch (error) {
        console.error('[MODIFY] 检查执行状态失败:', error)
      }
    }
  }
}

// 检查记录是否已被修改
const checkRecordModified = async (target, target_id, modifications) => {
  let detailUrl = ''
  if (target === 'badcase') {
    detailUrl = `/api/badcases/${target_id}`
  } else if (target === 'bug') {
    detailUrl = `/api/bugs/${target_id}`
  } else if (target === 'testcase') {
    detailUrl = `/api/testcases/${target_id}`
  }
  
  if (!detailUrl) return false
  
  const response = await fetch(detailUrl, { credentials: 'include' })
  if (!response.ok) return false
  
  const result = await response.json()
  if (result.error) {
    console.warn('[MODIFY] API 返回错误:', result.error)
    return false
  }
  
  const currentData = result[target] || result.badcase || result.bug || result.testcase
  if (!currentData) return false
  
  // 检查修改是否已生效
  for (const [field, newValue] of Object.entries(modifications)) {
    const currentValue = currentData[field]
    
    // 比较 assignee 字段时需要特殊处理
    if (field === 'assignee') {
      const currentAssigneeId = currentData.assignee_id
      const currentAssigneeName = currentData.assignee
      
      const matchesById = currentAssigneeId && currentAssigneeId.toString() === newValue.toString()
      const matchesByName = currentAssigneeName && currentAssigneeName.toString() === newValue.toString()
      
      if (!matchesById && !matchesByName) {
        return false
      }
    } else if (currentValue?.toString() !== newValue?.toString()) {
      return false
    }
  }
  
  return true
}

// 保存消息到数据库
const saveMessageToDb = async (messageData) => {
  if (!props.sessionId) return
  
  try {
    await addChatMessage(props.sessionId, messageData)
  } catch (error) {
    console.error('保存消息失败:', error)
  }
}

const sendText = async (rawText) => {
  const text = (rawText || '').trim()
  if (!text || isSending.value) return

  // 创建新的 AbortController
  abortController.value = new AbortController()
  isSending.value = true
  
  // 判断是否是“第一条用户消息”（用于生成会话标题）
  // 新会话里可能会预置提示/历史消息，不能用 messages.length 判断
  const isFirstUserMessage = !messages.value.some(m => m && m.isUser)
  
  // 添加用户消息
  const userMessage = {
    id: Date.now(),
    content: text,
    isUser: true,
    time: new Date().toLocaleTimeString()
  }
  messages.value.push(userMessage)
  
  // 保存用户消息到数据库
  await saveMessageToDb({
    is_user: true,
    content: userMessage.content
  })
  
  // 如果是第一条消息，异步生成会话标题
  if (isFirstUserMessage && props.sessionId) {
    generateSessionTitle(props.sessionId, userMessage.content)
      .then(res => {
        if (res.data.success) {
          console.log('[CHAT] 会话标题已生成:', res.data.title)
          // 通知父组件更新标题
          emit('title-updated', res.data.title)
        }
      })
      .catch(err => {
        console.error('[CHAT] 生成会话标题失败:', err)
      })
  }
  
  // 清空输入框
  const messageContent = text
  
  // 重置textarea高度
  nextTick(() => {
    autoResize()
  })
  
  scrollToBottom()
  
  // 根据选择的 Agent 模式发送请求
  if (selectedAgent.value === 'agent') {
    // 统一使用 ReAct 模式
    await handleReactAgentMode(messageContent)
  } else {
    // 使用普通对话模式 (流式)
    await handleChatMode(messageContent)
  }
  
  isSending.value = false
  abortController.value = null  // 清除 AbortController
}

// 发送消息（底部输入框）
const handleSend = async (e) => {
  e?.preventDefault()
  // 输入法组合状态下不发送
  if (isComposing.value) return
  const text = inputMessage.value
  inputMessage.value = ''
  await sendText(text)
}

const beginEditUserMessage = (msg) => {
  if (!msg) return
  editingUserMessageId.value = msg.id
  inlineInputMessage.value = msg.content || ''
  nextTick(() => {
    try {
      inlineTextareaRef.value?.focus?.()
    } catch (e) {}
  })
}

const cancelEditUserMessage = () => {
  editingUserMessageId.value = null
  inlineInputMessage.value = ''
}

const handleInlineSend = async (e) => {
  e?.preventDefault()
  if (isComposing.value) return
  const text = inlineInputMessage.value
  inlineInputMessage.value = ''
  editingUserMessageId.value = null
  await sendText(text)
}

const addNewLineInline = (e) => {
  // 保持 textarea 默认换行行为
  // 这里无需阻止默认
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
})

// 停止生成
const handleStop = () => {
  // 先把 UI 状态收敛（即使网络层 abort 还没抛异常）
  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg && !lastMsg.isUser) {
    finalizeRunningMessage(lastMsg, 'stopped')
  }

  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
    isSending.value = false
  }
}

// ReAct Agent 模式 - 调用后端 ReAct 接口 (流式处理)
const handleReactAgentMode = async (userMessage) => {
  console.log('[MODEL-DEBUG] 当前选择的模型:', selectedModel.value)
  
  const aiMessage = reactive({
    id: Date.now() + 1,
    isUser: false,
    content: '',
    time: new Date().toLocaleTimeString(),
    // 初始仅显示省略号「...」，等待 ReAct 流式事件接管
    understanding: '...',
    steps: [],
    finalResponse: '',
    reasoningContent: '',  // 思考过程内容
    showReasoning: true,   // 默认展开思考过程
    agentResult: { findings: [], recommendations: [], status: 'running' },
    allObservations: [],
    evidences: [],
    executionResults: [], // 执行结果数组
    searchResults: [] // 搜索结果数组
  })
  
  messages.value.push(aiMessage)
  scrollToBottom()
  
  try {
    console.log(`[CHAT-REACT] 调用 ReAct Agent 接口 (流式): ${userMessage}`)
    console.log('[MODEL-DEBUG] 请求参数 model:', selectedModel.value)
    const response = await fetch(`${BACKEND_BASE_URL}/api/agent/react`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      credentials: 'include',
      signal: abortController.value?.signal,  // 添加终止信号
      body: JSON.stringify({
        user_input: userMessage,
        model: selectedModel.value,
        stream: true,
        project_id: currentProjectId.value || props.projectId  // 传入项目 ID
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      
      const chunkText = decoder.decode(value, { stream: true })
      buffer += chunkText
      
      // 按行处理 SSE 数据
      let lines = buffer.split('\n')
      buffer = lines.pop() || '' // 留存最后一行可能不完整的数据

      for (const line of lines) {
        const trimmedLine = line.trim()
        if (!trimmedLine || trimmedLine.startsWith(':')) continue
        if (!trimmedLine.startsWith('data: ')) continue
        
        try {
          const jsonStr = trimmedLine.replace('data: ', '').trim()
          if (!jsonStr || jsonStr === '[DONE]') continue
          
          const chunk = JSON.parse(jsonStr)
          console.log('[CHAT-STREAM] 收到 Chunk:', chunk.type, chunk)
          
          if (chunk.type === 'heartbeat') continue
          
          // 处理不同类型的事件
          switch (chunk.type) {
            case 'status':
              // 仅用省略号表示「正在思考」，不展示具体中文文案
              if (!aiMessage.understanding) {
                aiMessage.understanding = '...'
              }
              break

            case 'intent':
              // 不在 UI 里展示“意图”，避免干扰用户；仅保留 todo/执行结果
              // 可按需在 console 里查看 chunk.intent
              break
            
            case 'step':
              // 一旦进入具体步骤，清理顶部省略号状态
              if (aiMessage.understanding === '...') {
                aiMessage.understanding = ''
              }
              const stepEvent = chunk.data
              if (!stepEvent) break
              console.log('[CHAT-STREAM] 收到 step 事件:', stepEvent.event, stepEvent)

              if (stepEvent.event === 'thought') {
                // thought 事件只用于内部状态更新，不展示
                // 不创建思考过程卡片
              } else if (stepEvent.event === 'reasoning') {
                // 文心 X1 / Qwen3 Max Thinking 等：流式追加思考过程，不截取
                const content = stepEvent.content ?? stepEvent.data ?? ''
                if (content !== '') {
                  aiMessage.reasoningContent = (aiMessage.reasoningContent || '') + content
                }
              } else if (stepEvent.event === 'immutable_field_rejection') {
                // 用户请求修改不可修改字段（如类型），后端已提前拦截，直接展示提示
                const msg = stepEvent.message || '该字段不可修改。可修改的字段包括：状态、期望结果、标题、优先级、复现步骤、负责人等。'
                aiMessage.agentResult.findings = [msg]
                aiMessage.finalResponse = `⚠️ ${msg}`
                aiMessage.agentResult.status = 'success'
                aiMessage.steps.forEach(s => {
                  s.status = 'skipped'
                  s.description = '已跳过（该字段不可修改）'
                })
              } else if (stepEvent.event === 'todos') {
                // 初始化 Todo 列表
                console.log('[CHAT-STREAM] 收到 todos 数据:', stepEvent.data)
                aiMessage.steps = (stepEvent.data || []).map((todo, idx) => {
                  const todoText = typeof todo === 'string' ? todo : (todo.title || todo.text || todo.content || `任务${idx+1}`)
                  console.log('[CHAT-STREAM] Todo项', idx, ':', todoText)
                  
                  // 提取工具名称，生成友好的标题
                  let friendlyTitle = todoText
                  const toolMatch = todoText.match(/使用\s*(\w+)\s*工具/)
                  if (toolMatch) {
                    friendlyTitle = toolMatch[1] // 提取工具名称
                  } else if (todoText.includes('database_query') || todoText.includes('查询')) {
                    friendlyTitle = 'database_query'
                  } else if (todoText.includes('grep') || todoText.includes('定位')) {
                    friendlyTitle = 'grep'
                  } else if (todoText.includes('modify') || todoText.includes('修改')) {
                    friendlyTitle = 'modify'
                  } else if (todoText.includes('create') || todoText.includes('创建')) {
                    friendlyTitle = 'create'
                  } else if (todoText.includes('browser_test') || todoText.includes('测试')) {
                    friendlyTitle = 'browser_test'
                  } else if (todoText.includes('search') || todoText.includes('搜索')) {
                    friendlyTitle = 'search'
                  }
                  
                  return {
                    title: friendlyTitle,
                    originalTodo: todoText, // 保存原始 todo 文本
                    status: 'pending',
                    description: '',
                    progressLog: []  // modify 等工具实时进度日志，用于流式展示
                  }
                })
                console.log('[CHAT-STREAM] 处理后的 steps:', aiMessage.steps)
              } else if (stepEvent.event === 'todo_start') {
                if (aiMessage.steps[stepEvent.index]) {
                  aiMessage.steps[stepEvent.index].status = 'running'
                }
              } else if (stepEvent.event === 'executing') {
                const runningStep = aiMessage.steps.find(s => s.status === 'running')
                if (runningStep) {
                  if (!runningStep.progressLog) runningStep.progressLog = []
                  // 后端 message 优先，用于流式进度/心跳
                  if (stepEvent.message) {
                    runningStep.description = stepEvent.message
                    runningStep.progressLog.push(stepEvent.message)
                    if (runningStep.progressLog.length > 20) runningStep.progressLog.shift()
                  }
                  // 无 message 时用工具名或字段列表做描述，避免一直只显示“修改中...”
                  if (stepEvent.tool === 'modify' && Array.isArray(stepEvent.fields) && stepEvent.fields.length > 0) {
                    const fieldText = stepEvent.fields.join('、')
                    if (!stepEvent.message) runningStep.description = `正在执行: modify（字段：${fieldText}）`
                    runningStep.toolCall = { name: `modify: ${fieldText}`, output: '执行中...' }
                  } else {
                    if (!stepEvent.message) runningStep.description = `正在执行: ${stepEvent.tool}`
                    runningStep.toolCall = { name: stepEvent.tool, output: '执行中...' }
                  }
                }
              } else if (stepEvent.event === 'observation') {
                console.log('[CHAT-STREAM] === 触发 observation 事件 ===')
                const outputData = stepEvent.data
                console.log('[CHAT-STREAM] 收到 observation 数据:', JSON.stringify(outputData, null, 2).substring(0, 500))
                console.log('[CHAT-STREAM] outputData 类型:', typeof outputData)
                console.log('[CHAT-STREAM] outputData.keys:', outputData ? Object.keys(outputData) : 'null')
                
                // 存储所有 observation 数据
                aiMessage.allObservations.push(outputData)
                
                // 查找正在运行的步骤，如果找不到就用最后一个步骤
                let runningStep = aiMessage.steps.find(s => s.status === 'running')
                if (!runningStep) {
                  // 如果没有 running 的步骤，找最后一个 modify 相关的步骤
                  runningStep = aiMessage.steps.slice().reverse().find(s => 
                    s.title && (s.title.includes('modify') || s.title === 'grep')
                  ) || aiMessage.steps[aiMessage.steps.length - 1]
                  console.log('[CHAT-STREAM] 没有找到 running 步骤，使用:', runningStep?.title)
                }
                
                if (runningStep) {
                  runningStep.toolCall = runningStep.toolCall || { name: '', output: '' }
                  runningStep.toolCall.output = typeof outputData === 'string' 
                    ? outputData 
                    : JSON.stringify(outputData, null, 2)
                  
                  // 收到结果后立即更新步骤状态为 completed
                  runningStep.status = 'completed'
                  runningStep.description = '已完成'
                  
                  // 提取搜索结果 - 执行辅揥器可能会调用搜索工具
                  let isSearchResult = false
                  if (outputData && typeof outputData === 'object') {
                    // 检查是否是搜索工具的结果
                    if (outputData.results && Array.isArray(outputData.results) && outputData.engine) {
                      // 来自搜索工具的结果
                      aiMessage.searchResults = outputData.results
                      isSearchResult = true
                      console.log('[CHAT-STREAM] ✅ 提取搜索结果:', outputData.results.length, '条')
                      console.log('[CHAT-STREAM] 搜索引擎:', outputData.engine, '查询:', outputData.query)
                    } else if (outputData.query && outputData.engine && Array.isArray(outputData.results)) {
                      // 线承搜索结果的另一种格式
                      aiMessage.searchResults = outputData.results
                      isSearchResult = true
                      console.log('[CHAT-STREAM] ✅ 提取搜索结果(格式2):', outputData.results.length, '条')
                    }
                  }
                  
                  // 只有非搜索结果才添加到 executionResults（避免显示原始 JSON）
                  if (!isSearchResult && runningStep.title) {
                    // 从title中提取工具名（title格式如："使用 grep 工具进行精准定位分析"）
                    const toolName = extractToolName(runningStep.title)
                    console.log('[TOOL-DEBUG] runningStep.title:', runningStep.title)
                    console.log('[TOOL-DEBUG] toolName:', toolName)
                    console.log('[TOOL-DEBUG] outputData:', outputData)
                                      
                    // 判断是否是grep或modify工具的返回结果
                    // 注意：后端返回的是 {success: true, data: {..., navigation: ...}} 
                    // 但流式传输时可能直接返回 data 部分
                    const toolData = outputData.data || outputData
                    console.log('[MODIFY-DEBUG] toolName:', toolName)
                    console.log('[MODIFY-DEBUG] toolData:', JSON.stringify(toolData, null, 2).substring(0, 800))
                    console.log('[MODIFY-DEBUG] toolData.batch_modify:', toolData.batch_modify)
                    console.log('[MODIFY-DEBUG] toolData.batch_results:', toolData.batch_results ? 'exists, length=' + toolData.batch_results.length : 'not exists')
                    console.log('[MODIFY-DEBUG] toolData.results:', toolData.results ? 'exists, length=' + toolData.results.length : 'not exists')
                                      
                    // 处理modify工具输出 - 使用modifyGroups替代modifyNavigation
                    if (toolName === 'modify' && toolData && typeof toolData === 'object') {
                      // 情况1: 批量修改结果 - 按 (plan_id, 连续性) 分组
                      // 注意：后端返回 batch_results，不是 results
                      const resultsArray = toolData.batch_results || toolData.results
                      console.log('[MODIFY] 检测批量修改数据: batch_modify=', toolData.batch_modify, 'results=', resultsArray ? resultsArray.length : 0)
                      if (toolData.batch_modify && resultsArray && Array.isArray(resultsArray) && resultsArray.length > 0) {
                        try {
                          // ===== 收集所有修改项（包含 plan_id）=====
                          const allItems = []
                          resultsArray.forEach(r => {
                            // 防御性检查 - batch_results 格式是 {target_id, plan_id, diff, ...}
                            // 不是 {id, result: {...}} 格式
                            const itemId = parseInt(r.target_id || r.id)
                            const itemPlanId = r.plan_id ? parseInt(r.plan_id) : null
                            
                            // 验证 ID 有效性
                            if (isNaN(itemId)) {
                              console.warn('[MODIFY] 跳过无效 ID:', r.target_id || r.id)
                              return
                            }
                            
                            // 检查是否有 diff
                            const rawDiff = r.diff || (r.result && r.result.diff) || []
                            console.log('[MODIFY-DEBUG] rawDiff:', rawDiff)
                            console.log('[MODIFY-DEBUG] r.modifications:', r.modifications)

                            // 按列表字段 / 详情字段拆分 diff
                            const listFieldDiff = []
                            const detailFieldDiff = []
                            rawDiff.forEach(fieldDiff => {
                              if (!fieldDiff || !fieldDiff.field) return
                              console.log('[MODIFY-DEBUG] fieldDiff.field:', fieldDiff.field, 'isDetail:', DETAIL_FIELDS.includes(fieldDiff.field))
                              if (DETAIL_FIELDS.includes(fieldDiff.field)) {
                                detailFieldDiff.push(fieldDiff)
                              } else {
                                listFieldDiff.push(fieldDiff)
                              }
                            })
                            console.log('[MODIFY-DEBUG] detailFieldDiff:', detailFieldDiff.length, 'listFieldDiff:', listFieldDiff.length)

                            const baseItemInfo = {
                              target_id: itemId,
                              plan_id: itemPlanId,
                              target: r.target || toolData.target || 'badcase',
                              modifications: r.modifications || (r.result && r.result.modifications) || {},
                              confirmation_required: r.confirmation_required !== false,
                              success: r.success === true
                            }

                            // 如果同一条记录同时修改了列表和详情字段，则拆成两个 item
                            if (listFieldDiff.length > 0) {
                              allItems.push({
                                ...baseItemInfo,
                                diff: listFieldDiff
                              })
                            }
                            if (detailFieldDiff.length > 0) {
                              allItems.push({
                                ...baseItemInfo,
                                diff: detailFieldDiff
                              })
                            }
                          })
                          
                          if (allItems.length === 0) {
                            console.warn('[MODIFY] 没有有效的修改项')
                          } else {
                            // ===== 按 plan_id 分组 =====
                            const planGroups = {}
                            allItems.forEach(item => {
                              const planKey = item.plan_id !== null ? String(item.plan_id) : 'unplanned'
                              if (!planGroups[planKey]) {
                                planGroups[planKey] = []
                              }
                              planGroups[planKey].push(item)
                            })
                            
                            // ===== 在每个 plan_id 组内按连续性分组 =====
                            const modifyGroups = []
                            Object.entries(planGroups).forEach(([planId, items]) => {
                              // 按 target_id 数值排序
                              items.sort((a, b) => a.target_id - b.target_id)
                              
                              // 分组连续的项（ID 差值为 1）
                              let currentGroup = []
                              
                              items.forEach((item, idx) => {
                                if (idx === 0) {
                                  // 第一项直接加入
                                  currentGroup.push(item)
                                } else {
                                  const prevItem = items[idx - 1]
                                  const idDiff = item.target_id - prevItem.target_id
                                  
                                  if (idDiff === 1) {
                                    // 连续：加入当前组
                                    currentGroup.push(item)
                                  } else {
                                    // 不连续：保存当前组，开始新组
                                    if (currentGroup.length > 0) {
                                      modifyGroups.push({
                                        plan_id: planId === 'unplanned' ? null : parseInt(planId),
                                        items: [...currentGroup]  // 复制数组
                                      })
                                    }
                                    currentGroup = [item]
                                  }
                                }
                              })
                              
                              // 保存最后一组
                              if (currentGroup.length > 0) {
                                modifyGroups.push({
                                  plan_id: planId === 'unplanned' ? null : parseInt(planId),
                                  items: [...currentGroup]  // 复制数组
                                })
                              }
                            })
                            
                            // 使用 Vue.set 风格更新，确保响应式
                            aiMessage.modifyGroups = Object.freeze([...modifyGroups])
                            aiMessage.modifyNavigation = {
                              batch_modify: true,
                              batch_results: [...allItems],
                              batch_count: allItems.length,
                              target: allItems[0]?.target || toolData.target || 'badcase'
                            }
                            console.log('[MODIFY] 生成 modifyGroups:', modifyGroups.length, '个分组, 共', allItems.length, '项')
                          }
                        } catch (err) {
                          console.error('[MODIFY] 分组处理异常:', err)
                        }
                      }
                      // 情况2: 单个需要确认的预览模式
                      else if (toolData.confirmation_required && toolData.diff) {
                        aiMessage.modifyNavigation = {
                          target: toolData.target,
                          target_id: toolData.target_id,
                          diff: toolData.diff,
                          modifications: toolData.modifications,
                          confirmation_required: true
                        }
                        console.log('[MODIFY] 存储沙箱预览导航:', aiMessage.modifyNavigation)
                      }
                      // 情况3: 单个已执行的修改结果
                      else if (toolData.diff && toolData.before && toolData.after) {
                        aiMessage.modifyNavigation = {
                          target: toolData.target || 'bug',
                          target_id: toolData.target_id,
                          diff: toolData.diff,
                          before: toolData.before,
                          after: toolData.after,
                          plan_id: toolData.before?.plan_id,
                          success: toolData.success,
                          message: toolData.message
                        }
                        console.log('[MODIFY] 存储单个修改导航:', aiMessage.modifyNavigation)
                      }
                    }
                    
                    // 处理create工具输出
                    if (toolName === 'create' && toolData && typeof toolData === 'object') {
                      if (toolData.confirmation_required && toolData.preview) {
                        // 存储create预览数据
                        aiMessage.createPreview = {
                          target: toolData.target,
                          preview: toolData.preview
                        }
                        console.log('[CREATE] 存储create预览:', aiMessage.createPreview)
                      }
                    }
                                      
                    // 处理grep工具输出
                    if (toolName === 'grep' && toolData && typeof toolData === 'object') {
                      console.log('[GREP-DEBUG] 进入grep处理分支')
                      console.log('[GREP-DEBUG] outputData:', outputData)
                      console.log('[GREP-DEBUG] toolData:', toolData)
                      console.log('[GREP-DEBUG] toolData keys:', Object.keys(toolData))
                      
                      // grep工具返回的是结构化数据，提取关键信息
                      let summaryText = ''
                      
                      // 提取总结信息 - 支持两种数据结构
                      const summary = toolData.summary || toolData.data?.summary
                      if (summary) {
                        summaryText = summary
                      } else {
                        // 构造简要总结
                        const parts = []
                        if (toolData.plan_tree) {
                          parts.push(`📊 计划树: ${toolData.plan_tree.total_plans || 0}个计划`)
                        }
                        if (toolData.badcase_analysis) {
                          parts.push(`🐛 BadCase: ${toolData.badcase_analysis.length || 0}条`)
                        }
                        if (toolData.bug_location) {
                          parts.push(`🔍 Bug: ${toolData.bug_location.length || 0}条`)
                        }
                        summaryText = parts.join(' | ')
                      }
                      
                      aiMessage.executionResults.push({ 
                        step: runningStep.title, 
                        text: summaryText,
                        success: outputData.success || toolData.success
                      })
                      
                      // 处理导航指令（如果存在）
                      console.log('[GREP-NAV] outputData:', outputData)
                      console.log('[GREP-NAV] toolData:', toolData)
                      
                      // navigation 可能在不同层级
                      const navigationData = outputData.navigation || toolData.navigation || toolData.data?.navigation
                      console.log('[GREP-NAV] navigationData:', navigationData)
                      
                      if (navigationData) {
                        console.log('[GREP-NAV] 收到导航指令:', navigationData)
                        
                        // 存储navigation信息到message对象，供"关键发现"使用
                        aiMessage.navigation = navigationData
                        console.log('[GREP-NAV] 已存储navigation到aiMessage:', aiMessage.navigation)
                        
                        // 单个Bug直接跳转，多个Bug等待用户点击
                        handleNavigation(navigationData)
                      } else {
                        console.log('[GREP-NAV] 未找到navigation字段')
                      }
                    } else {
                      // 其他工具，直接stringify
                      const resultStr = typeof outputData === 'string' 
                        ? outputData 
                        : JSON.stringify(outputData, null, 2)
                      aiMessage.executionResults.push({ 
                        step: runningStep.title, 
                        text: resultStr 
                      })
                    }
                  }
                }
              } else if (stepEvent.event === 'evidence') {
                // 捕获执行证据
                console.log('[CHAT-STREAM] 收到 evidence 数据:', stepEvent.data, typeof stepEvent.data)
                if (stepEvent.data) {
                  let evidenceData = stepEvent.data
                  // 如果是字符串，尝试解析为 JSON
                  if (typeof evidenceData === 'string') {
                    try {
                      // 移除可能的前缀（如 ✅ ）
                      let cleanData = evidenceData.replace(/^[✅❌⏳🔧]\s*/, '')
                      // 将 Python 字典格式的单引号转换为 JSON 双引号
                      cleanData = cleanData
                        .replace(/'/g, '"')
                        .replace(/None/g, 'null')
                        .replace(/True/g, 'true')
                        .replace(/False/g, 'false')
                      evidenceData = JSON.parse(cleanData)
                      console.log('[CHAT-STREAM] 解析后的 evidence:', evidenceData)
                    } catch (e) {
                      console.error('[CHAT-STREAM] evidence 解析失败:', e, evidenceData)
                      // 如果解析失败，构造一个默认对象
                      evidenceData = {
                        tool_used: '未知工具',
                        status: 'completed',
                        raw_data: evidenceData
                      }
                    }
                  }
                  aiMessage.evidences.push({
                    tool: evidenceData.tool_used,
                    data: evidenceData
                  })
                }
              } else if (stepEvent.event === 'finding') {
                if (aiMessage.agentResult && !aiMessage.agentResult.findings.includes(stepEvent.data)) {
                  aiMessage.agentResult.findings.push(stepEvent.data)
                }
              } else if (stepEvent.event === 'todo_end') {
                if (aiMessage.steps[stepEvent.index]) {
                  aiMessage.steps[stepEvent.index].status = 'completed'
                  aiMessage.steps[stepEvent.index].description = '已完成'
                }
              } else if (stepEvent.event === 'skip') {
                // 跳过的步骤标记为 skipped 状态
                const runningStep = aiMessage.steps.find(s => s.status === 'running')
                if (runningStep) {
                  runningStep.status = 'skipped'
                  runningStep.description = '已跳过'
                }
              } else if (stepEvent.event === 'done') {
                aiMessage.agentResult.status = 'success'
                aiMessage.agentResult.execution_time = stepEvent.duration
                aiMessage.agentResult.steps_count = stepEvent.steps_count || 0
                if (stepEvent.thinking_time != null && stepEvent.thinking_time >= 0) {
                  aiMessage.agentResult.thinking_time = stepEvent.thinking_time
                }
                if (stepEvent.summary && typeof stepEvent.summary === 'string') {
                  aiMessage.agentResult.summaryText = stepEvent.summary.trim()
                }
                
                // 确保所有步骤状态都更新为 completed
                aiMessage.steps.forEach((step, idx) => {
                  if (step.status !== 'completed') {
                    step.status = 'completed'
                    step.description = '已完成'
                  }
                })
                
                // 构建最终输出摘要
                let finalResp = ''
                
                // 添加所有发现的内容
                const allFindings = stepEvent.findings && stepEvent.findings.length > 0 
                  ? stepEvent.findings 
                  : aiMessage.agentResult.findings
                
                // 如果没有 findings，尝试从所有观察结果中聚合提取
                const displayFindings = allFindings.length > 0 ? allFindings : []
                if (displayFindings.length === 0 && aiMessage.allObservations.length > 0) {
                  for (const obs of aiMessage.allObservations) {
                    if (typeof obs === 'object' && obs !== null) {
                      // 优先提取summary字段（人类可读）
                      if (obs.summary && typeof obs.summary === 'string') {
                        const summaryLines = obs.summary.split('\n').filter(line => line.trim())
                        for (const line of summaryLines) {
                          if (!displayFindings.includes(line)) {
                            displayFindings.push(line)
                          }
                        }
                        continue  // 已提取summary，跳过其他字段
                      }
                      
                      // 从观察对象中提取关键字段（排除data原始对象）
                      const priorityKeys = ['bugs_found', 'elements_found', 'issues_found', 'errors_found', 'elements', 'output', 'findings', 'page_content', 'text', 'content', 'message']
                      for (const key of priorityKeys) {
                        if (key in obs && obs[key]) {
                          const value = obs[key]
                          if (typeof value === 'string') {
                            // 字符串直接添加
                            if (value.trim() && !displayFindings.includes(value.trim())) {
                              displayFindings.push(value.trim())
                            }
                          } else if (Array.isArray(value)) {
                            // 数组元素逐个处理
                            for (const item of value) {
                              const itemStr = typeof item === 'string' ? item : (item.title || item.name || item.description || JSON.stringify(item))
                              if (itemStr && !displayFindings.includes(itemStr)) {
                                displayFindings.push(itemStr)
                              }
                            }
                          } else if (typeof value === 'object') {
                            // 对象转人类可读的摘要
                            const summary = formatObjectToSummary(value)
                            if (summary && !displayFindings.includes(summary)) {
                              displayFindings.push(summary)
                            }
                          }
                        }
                      }
                    } else if (typeof obs === 'string') {
                      // 直接字符串观察结果
                      if (obs.trim() && !displayFindings.includes(obs.trim())) {
                        displayFindings.push(obs.trim())
                      }
                    }
                  }
                }
                
                // 将findings保存到agentResult，不再拼接到finalResponse
                if (displayFindings.length > 0) {
                  aiMessage.agentResult.findings = displayFindings
                }
                
                // 若为提前拦截（如不可修改字段），steps_count 为 0，直接展示 findings 作为最终说明
                if ((stepEvent.steps_count === 0 || !stepEvent.steps_count) && displayFindings.length > 0) {
                  aiMessage.finalResponse = '⚠️ ' + displayFindings[0]
                } else {
                  finalResp += `执行统计:\n`
                  finalResp += `  • 完成步骤: ${stepEvent.steps_count || aiMessage.steps.length} 个\n`
                  finalResp += `  • 耗时: ${Number(stepEvent.duration || 0).toFixed(2)}s\n`
                  finalResp += `\n任务执行成功`
                  aiMessage.finalResponse = finalResp
                }
              } else if (stepEvent.event === 'error') {
                aiMessage.finalResponse = `❌ 错误: ${stepEvent.message}`
                aiMessage.agentResult.status = 'failed'
              }
              break
              
            case 'error':
              aiMessage.finalResponse = `❌ 接口错误: ${chunk.message}`
              break
          }
          
          // 强制触发滚动和更新
          scrollToBottom()
        } catch (e) {
          console.error('[CHAT-STREAM] 解析失败:', e, trimmedLine)
        }
      }
    }
  } catch (error) {
    console.error('ReAct 执行失败:', error)
    // 如果用户已点过停止（我们已在 handleStop 里收敛 UI），这里不要再覆盖成错误
    if (aiMessage?.agentResult?.status === 'cancelled') {
      // noop
    } else {
      const msg = String(error?.message || error || '')
      const msgLower = msg.toLowerCase()
      const aborted =
        abortController.value?.signal?.aborted ||
        error?.name === 'AbortError' ||
        msgLower.includes('aborted') ||
        msgLower.includes('bodystreambuffer')

      if (aborted) {
        finalizeRunningMessage(aiMessage, 'stopped')
      } else {
        finalizeRunningMessage(aiMessage, 'failed')
        aiMessage.finalResponse = `错误: ${error.message || '未知错误'}`
      }
    }
  }
  
  // 保存最终结果到数据库
  await saveMessageToDb({
    is_user: false,
    content: aiMessage.finalResponse || aiMessage.understanding || '处理完成',
    understanding: aiMessage.understanding,
    reasoning: aiMessage.reasoningContent || '',
    steps: JSON.stringify(aiMessage.steps),
    execution_results: JSON.stringify(aiMessage.executionResults || []),
    agent_result: JSON.stringify(aiMessage.agentResult || {}),
    evidences: JSON.stringify(aiMessage.evidences || []),
    navigation: JSON.stringify(aiMessage.navigation || null),
    modify_navigation: JSON.stringify(aiMessage.modifyNavigation || null),  // 保存 modifyNavigation
    modify_groups: JSON.stringify(aiMessage.modifyGroups || null),  // 保存 modifyGroups
    final_response: aiMessage.finalResponse
  })
}

// Agent 模式 - 调用后端 Agent 接口
const handleAgentMode = async (userMessage) => {
  const aiMessage = {
    id: Date.now() + 1,
    isUser: false,
    time: new Date().toLocaleTimeString(),
    understanding: '...',
    steps: [],
    finalResponse: '',
    agentResult: null
  }
  
  messages.value.push(aiMessage)
  scrollToBottom()
  
  try {
    // 调用后端 Agent 接口
    console.log(`[CHAT-EXECUTE] 正在调用 /api/agent/execute 接口: ${userMessage}`)
    // 使用 fetch 调用 /api/agent/execute（不是 ReAct）
    const response = await fetch(`${BACKEND_BASE_URL}/api/agent/execute`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        user_input: userMessage,
        model: selectedModel.value,
        project_id: currentProjectId.value || props.projectId,  // 传入项目ID
        conversation_history: messages.value.map(m => ({
          role: m.isUser ? 'user' : 'assistant',
          content: m.content || m.finalResponse || m.understanding
        })),
        agent_mode: 'auto'
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const data = await response.json()
    
    if (data.code === 200) {
      const resultData = data.data
      
      // 更新 AI 理解
      aiMessage.understanding = `已识别【${resultData.detected_agent}】【意图${resultData.detected_intent}】`
      
      // 添加执行步骤
      if (resultData.result && resultData.result.data) {
        aiMessage.steps = [
          {
            title: `${resultData.detected_agent} - ${resultData.detected_intent}`,
            description: `执行步骤数: ${resultData.result.data.steps_executed || 0}`,
            status: 'completed'
          }
        ]
      }
      
      // 保存 Agent 结果
      aiMessage.agentResult = resultData.result && resultData.result.data ? resultData.result.data : null
      
      // 设置最终回复
      if (resultData.result && resultData.result.data && resultData.result.data.bugs_found && resultData.result.data.bugs_found.length > 0) {
        aiMessage.finalResponse = `已发现 ${resultData.result.data.bugs_found.length} 个 Bug，点击下方「保存 Bug」按钮可保存到数据库`
      } else if (resultData.result && resultData.result.message) {
        aiMessage.finalResponse = resultData.result.message
      } else if (resultData.result && resultData.result.data) {
        aiMessage.finalResponse = `测试执行并分析完成。执行耗时: ${resultData.result.data.execution_duration?.toFixed(2)}s`
      } else {
        aiMessage.finalResponse = '已接收你的输入，正在处理...'
      }
      
      scrollToBottom()
    } else {
      aiMessage.finalResponse = `错误: ${data.message}`
    }
  } catch (error) {
    console.error('[CHAT-EXECUTE] Agent 执行失败:', error)
    aiMessage.finalResponse = `错误: ${error.message || '未知错误'}`
  }
  
  // 保存 AI 消息到数据库
  await saveMessageToDb({
    is_user: false,
    content: aiMessage.finalResponse || aiMessage.understanding || '正在处理...', // ✅ 添加字段
    understanding: aiMessage.understanding,
    steps: JSON.stringify(aiMessage.steps),
    final_response: aiMessage.finalResponse
  })
  
  scrollToBottom()
}

// 普通对话模式 - 调用后端聊天接口 (流式处理)
const handleChatMode = async (userMessage) => {
  const aiMessage = {
    id: Date.now() + 1,
    isUser: false,
    content: '',
    time: new Date().toLocaleTimeString(),
    understanding: '',
    steps: [],
    finalResponse: ''
  }
  
  messages.value.push(aiMessage)
  scrollToBottom()
  
  try {
    console.log(`[CHAT] 调用聊天接口 (流式): ${userMessage}`)
    const response = await fetch(`${BACKEND_BASE_URL}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      signal: abortController.value?.signal,  // 添加终止信号
      body: JSON.stringify({
        inputMessage: userMessage,
        model: selectedModel.value,
        projectId: currentProjectId.value || props.projectId
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        
        try {
          const jsonStr = line.replace('data: ', '').trim()
          if (!jsonStr) continue
          const chunk = JSON.parse(jsonStr)
          
          if (chunk.type === 'start') {
            // 统一用「...」做占位，不展示具体中文提示
            aiMessage.understanding = '...'
          } else if (chunk.type === 'chunk') {
            if (aiMessage.understanding === '...') {
              aiMessage.understanding = ''
            }
            aiMessage.finalResponse += chunk.content
          } else if (chunk.type === 'agent_start') {
            // 不再在 UI 展示「正在调用 Agent」，只作为内部事件
            aiMessage.understanding = '...'
          } else if (chunk.type === 'result') {
            // Agent 执行结果处理
            const result = chunk.data
            if (result.message) {
              aiMessage.finalResponse += `\n\n【Agent 结果】: ${result.message}`
            }
            if (result.data && typeof result.data === 'object') {
              aiMessage.steps.push({
                title: 'Agent 执行结果',
                description: '详细数据已记录',
                status: 'completed',
                toolCall: { name: 'AgentResult', output: JSON.stringify(result.data, null, 2) }
              })
            }
          } else if (chunk.type === 'error') {
            aiMessage.finalResponse += `\n\n❌ 错误: ${chunk.message}`
          }
          
          scrollToBottom()
        } catch (e) {
          console.warn('解析聊天流数据失败:', e, line)
        }
      }
    }
  } catch (error) {
    console.error('聊天执行失败:', error)
    aiMessage.finalResponse = `错误: ${error.message || '未知错误'}`
  }
  
  // 保存到数据库
  await saveMessageToDb({
    is_user: false,
    content: aiMessage.finalResponse || aiMessage.understanding || '处理完成',
    understanding: aiMessage.understanding,
    steps: JSON.stringify(aiMessage.steps),
    final_response: aiMessage.finalResponse
  })
}

// 延迟函数
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// 保存 Bug
const handleSaveBugs = async (agentResult) => {
  try {
    // 需要于整个应用中获取 projectId
    // 暂时使用模拟 projectId
    const projectId = currentProjectId.value || props.projectId || 1
    
    if (!projectId) {
      alert('没有项目信息，不能保存 Bug')
      return
    }
    
    const bugsToSave = agentResult.bugs_found.map(bug => ({
      title: bug.title,
      severity: bug.severity || 'medium',
      priority: bug.priority || 'medium',
      description: bug.description,
      steps_to_reproduce: bug.steps_to_reproduce || '',
      expected: bug.expected || '',
      actual: bug.actual || '',
      source: 'agent_test'
    }))
    
    console.log('[CHAT] 正在保存 Bug...', bugsToSave)
    
    const response = await saveAgentBugs({
      project_id: projectId,
      bugs: bugsToSave
    })
    
    if (response.data.code === 200) {
      alert(`成功保存 ${response.data.data.saved_count} 个 Bug`)
      console.log('Bug ID:', response.data.data.bug_ids)
    } else {
      alert(`保存失败: ${response.data.message}`)
    }
  } catch (error) {
    console.error('Bug 保存失败:', error)
    alert(`错误: ${error.message}`)
  }
}
const addNewLine = (e) => {
  e.preventDefault()
  inputMessage.value += '\n'
  autoResize()
}

// 自动调整textarea高度
const autoResize = () => {
  const textarea = textareaRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 44), 200)
    textarea.style.height = newHeight + 'px'
  }
}

onMounted(() => {
  scrollToBottom()
  // 初始化textarea高度
  nextTick(() => {
    autoResize()
  })
  // 加载会话消息
  loadSessionMessages()
  
  // 监听修改取消/确认事件
  window.addEventListener('modify-cancelled', handleModifyCancelled)
  window.addEventListener('modify-confirmed', handleModifyConfirmed)
})

// 处理修改取消事件
const handleModifyCancelled = (event) => {
  const { targetId } = event.detail
  console.log('[MODIFY] 收到取消事件，targetId:', targetId)
  
  // 找到对应的 modifyNavigation 并标记为已处理
  messages.value.forEach(msg => {
    if (msg.modifyNavigation && msg.modifyNavigation.target_id === targetId) {
      msg.modifyNavigation.cancelled = true
      msg.modifyNavigation.success = true  // 标记为已处理，再次点击只定位
      console.log('[MODIFY] 已标记消息为已取消:', msg.id)
    }
  })
}

// 处理修改确认事件
const handleModifyConfirmed = (event) => {
  const { targetId } = event.detail
  const intTargetId = parseInt(targetId)
  console.log('[MODIFY] 收到确认事件，targetId:', intTargetId)
  
  if (isNaN(intTargetId)) {
    console.error('[MODIFY] 无效的 targetId:', targetId)
    return
  }
  
  // 找到对应的 modifyNavigation 或 modifyGroups 并标记为已执行
  messages.value.forEach((msg, msgIdx) => {
    let updated = false
    
    // 处理 modifyGroups
    if (msg.modifyGroups && Array.isArray(msg.modifyGroups)) {
      msg.modifyGroups.forEach((group, groupIdx) => {
        if (!group.items || !Array.isArray(group.items)) return
        
        const itemIdx = group.items.findIndex(i => i.target_id === intTargetId)
        if (itemIdx !== -1) {
          // 创建新对象触发响应式更新
          const newItem = {
            ...group.items[itemIdx],
            confirmation_required: false,
            success: true
          }
          // 替换数组中的项
          group.items.splice(itemIdx, 1, newItem)
          updated = true
          console.log('[MODIFY] modifyGroups 中标记项为已执行:', intTargetId)
          
          // 检查组内是否全部确认完成
          const allGroupConfirmed = group.items.every(i => i.confirmation_required === false || i.success === true)
          if (allGroupConfirmed) {
            console.log('[MODIFY] 该分组全部确认完成, plan_id:', group.plan_id)
          }
        }
      })
    }
    
    // 处理 modifyNavigation
    if (msg.modifyNavigation) {
      // 批量修改：标记 batch_results 中对应的项
      if (msg.modifyNavigation.batch_modify && msg.modifyNavigation.batch_results) {
        const resultIdx = msg.modifyNavigation.batch_results.findIndex(r => r.target_id === intTargetId)
        if (resultIdx !== -1) {
          // 创建新对象触发响应式更新
          msg.modifyNavigation.batch_results.splice(resultIdx, 1, {
            ...msg.modifyNavigation.batch_results[resultIdx],
            confirmation_required: false,
            success: true
          })
          updated = true
          console.log('[MODIFY] 批量修改中标记项为已执行:', intTargetId)
          
          // 检查是否所有项都已确认
          const allConfirmed = msg.modifyNavigation.batch_results.every(r => r.confirmation_required === false || r.success === true)
          if (allConfirmed) {
            console.log('[MODIFY] 批量修改全部确认完成')
          }
        }
      }
      // 单个修改：标记整个 modifyNavigation
      else if (msg.modifyNavigation.target_id === intTargetId) {
        msg.modifyNavigation = {
          ...msg.modifyNavigation,
          success: true,
          confirmation_required: false
        }
        updated = true
        console.log('[MODIFY] 已标记消息为已执行:', msg.id)
      }
    }
    
    // 触发响应式更新
    if (updated) {
      messages.value[msgIdx] = { ...messages.value[msgIdx] }
    }
  })
}

// 组件销毁时移除事件监听
onUnmounted(() => {
  window.removeEventListener('modify-cancelled', handleModifyCancelled)
  window.removeEventListener('modify-confirmed', handleModifyConfirmed)
})

// 监听 sessionId 变化，重新加载消息
watch(() => props.sessionId, (newSessionId) => {
  if (newSessionId) {
    loadSessionMessages()
  } else {
    messages.value = []
  }
})
</script>

<style scoped>
.simple-chat-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: #1e1e1e;
  color: #d4d4d4;
  min-height: 0;
  overflow: hidden;
  margin: 0;
  padding: 0;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #888;
  font-size: 14px;
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.message-block {
  display: flex;
  flex-direction: column;
  width: 100%;
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

/* AI理解意图loading动画：左侧三个点，尽量弱化卡片感 */
.ai-understanding {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0;
  background: transparent;
  margin: 4px 0;
}

.ai-understanding-text {
  min-width: 18px;
  text-align: left;
  color: #e5e7eb;
  font-size: 12px;
  letter-spacing: 2px;
  animation: thinkingPulse 1s ease-in-out infinite;
}

@keyframes thinkingPulse {
  0% { opacity: 0.3; }
  50% { opacity: 1; }
  100% { opacity: 0.3; }
}


.loading-dots {
  display: inline-flex;
  gap: 4px;
  margin-left: 8px;
}

.loading-dots .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #888;
  animation: dotPulse 1.4s infinite ease-in-out both;
}

.loading-dots .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots .dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes dotPulse {
  0%, 80%, 100% {
    opacity: 0.3;
    transform: scale(0.8);
  }
  40% {
    opacity: 1;
    transform: scale(1);
  }
}

.message-author {
  font-weight: 600;
  font-size: 13px;
  color: #d4d4d4;
}

.message-time {
  font-size: 11px;
  color: #888;
}

/* 用户消息样式 */
.user-message-block {
  display: flex;
  flex-direction: column;
  align-items: stretch; /* 让“用户输入条”占满整行 */
  width: 100%;
}

.user-message-bubble {
  width: 100%;
  max-width: 100%;
  padding: 12px 16px;
  background: rgba(148, 163, 184, 0.10); /* 未选中：更轻的浅灰底 */
  color: #e5e7eb;
  border: 1px solid rgba(148, 163, 184, 0.18); /* 未选中：更淡的细边框 */
  border-radius: 10px; /* 接近输入框的圆角 */
  line-height: 1.5;
  white-space: pre-wrap;
  overflow: visible; /* 避免底部阴影/截断观感 */
  word-wrap: break-word;
  word-break: break-word;
  font-size: 14px;
  box-shadow: none; /* 不要阴影 */
  outline: none; /* 交给 focus 样式 */
  transition: background 0.15s ease, border-color 0.15s ease;
}

/* 选中态（点击获得焦点）——对齐你第二张图的“更亮底色 + 更清晰边框” */
.user-message-bubble:focus {
  background: rgba(148, 163, 184, 0.16);
  border-color: rgba(148, 163, 184, 0.32);
}

/* 键盘导航时给一个更明确的可见焦点（不影响鼠标点击观感） */
.user-message-bubble:focus-visible {
  border-color: rgba(96, 165, 250, 0.55);
}

/* 用户消息进入编辑态：容器占满整行，并与底部输入框统一背景/边框 */
.inline-composer {
  width: 100%;
}

.inline-composer .input-box-wrapper {
  width: 100%;
  background: #252526;
  border: 1px solid #3e3e3e;
  border-radius: 8px;
  overflow: hidden;
}

.inline-composer .input-box-wrapper:focus-within {
  border-color: #007acc;
  box-shadow: 0 0 0 1px #007acc;
}

/* AI消息样式 */
.ai-message-block {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* 步骤列表 */
.ai-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.step-item {
  padding: 12px;
  background: #252526;
  border-radius: 6px;
  border-left: 3px solid #666;
  transition: all 0.3s ease;
}

.step-item.running {
  border-left-color: #ffa500;
  background: #2d2d2d;
}

.step-item.completed {
  border-left-color: #4caf50;
}

.step-item.error {
  border-left-color: #f44336;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.step-icon {
  font-size: 16px;
}

.step-title {
  font-weight: 500;
  color: #d4d4d4;
  font-size: 13px;
}

.step-description {
  color: #aaa;
  font-size: 12px;
  margin-top: 4px;
  margin-left: 24px;
}

/* 工具调用 */
.tool-call {
  margin-top: 8px;
  margin-left: 24px;
  padding: 8px 12px;
  background: #1e1e1e;
  border-radius: 4px;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.tool-icon {
  font-size: 14px;
}

.tool-name {
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  font-size: 12px;
  color: #4fc3f7;
}

.tool-level {
  font-size: 11px;
  color: #999;
  margin-left: auto;
  padding: 2px 6px;
  background: #1e1e1e;
  border-radius: 3px;
}

/* 分层工具样式 */
.tool-call.level-l1 {
  border-left: 2px solid #ff9800;
  background: #2a2420;
}

.tool-call.level-l2 {
  border-left: 2px solid #00bcd4;
  background: #1a2627;
}

.tool-call.level-l3 {
  border-left: 2px solid #4caf50;
  background: #1b2718;
}

/* 自我修正信息 */
.correction-info {
  margin-top: 8px;
  margin-left: 24px;
  padding: 10px 12px;
  background: #2a2a2a;
  border-left: 2px solid #ff5722;
  border-radius: 4px;
}

.correction-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.correction-icon {
  font-size: 14px;
}

.correction-title {
  font-weight: 500;
  color: #ff5722;
  font-size: 12px;
}

.correction-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.correction-item {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: #aaa;
}

.correction-item .label {
  color: #999;
  font-weight: 500;
  min-width: 40px;
}

.correction-item .value {
  color: #d4d4d4;
  flex: 1;
}

.tool-output {
  margin-top: 4px;
}

.tool-output pre {
  margin: 0;
  padding: 8px;
  background: #0d1117;
  border-radius: 4px;
  color: #aaa;
  font-size: 12px;
  font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
  overflow-x: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* AI最终回复 */
.ai-response {
  padding: 12px 16px;
  background: #2d2d2d;
  border-radius: 6px;
}

.response-text,
.ai-response-text {
  color: #d4d4d4;
  line-height: 1.6;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
}

.input-container {
  flex-shrink: 0;
  padding: 16px;
  background: #1e1e1e;
  position: sticky;
  bottom: 0;
  z-index: 100;
}

.input-box-wrapper {
  background: #252526;
  border: 1px solid #3e3e3e;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  transition: border-color 0.2s, box-shadow 0.2s;
  overflow: hidden;
}

.input-box-wrapper:focus-within {
  border-color: #007acc;
  box-shadow: 0 0 0 1px #007acc;
}

.message-input {
  width: 100%;
  padding: 12px 14px;
  background: transparent;
  border: none;
  color: #d4d4d4;
  font-size: 14px;
  font-family: inherit;
  resize: none;
  outline: none;
  line-height: 1.5;
  min-height: 44px;
  max-height: 200px;
  overflow-y: auto;
  box-sizing: border-box;
}

.message-input::placeholder {
  color: #666;
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 8px;               /* 进一步压缩高度 */
  background: transparent;         /* 去掉浅灰载体 */
  border-top: none;               /* 去掉细线 */
}

.footer-left {
  display: flex;
  gap: 8px;
  align-items: center;
}

.selector-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: rgba(226, 232, 240, 0.7);
  font-size: 11px;
}

.selector-label {
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.footer-select {
  /* 默认（未选中）：更浅灰，更像 Cursor 输入区工具条 */
  background: rgba(148, 163, 184, 0.10);
  border: 1px solid rgba(148, 163, 184, 0.18);
  color: #e5e7eb;
  font-size: 12px;        /* 选择器更大一点 */
  padding: 2px 10px;      /* 增大可点区域 */
  border-radius: 8px;
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.footer-select:hover {
  background: rgba(148, 163, 184, 0.14);
  border-color: rgba(148, 163, 184, 0.28);
}

.footer-select:focus {
  background: rgba(148, 163, 184, 0.14);
  border-color: rgba(148, 163, 184, 0.32);
}

/* 下拉菜单（Electron/Chromium 下通常可生效） */
.footer-select option {
  /* 展开菜单保持 Cursor：深色底 + 白字 */
  background: #1f1f1f;
  color: #e6e6e6;
}

.footer-right {
  display: flex;
  align-items: center;
}

.send-icon-button {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: #ffffff;
  border: 1px solid #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.12s ease, opacity 0.12s ease, background 0.12s ease, border-color 0.12s ease;
}

.send-icon-button:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #f8fafc;
  transform: scale(1.05);
}

.send-icon-button:active:not(:disabled) {
  transform: scale(0.95);
}

.send-icon-button:disabled {
  background: rgba(255, 255, 255, 0.30);
  border-color: rgba(255, 255, 255, 0.30);
  cursor: not-allowed;
  opacity: 1;
}

.send-icon-img {
  width: 11px;
  height: 11px;
  display: block;
  filter: brightness(0) saturate(100%);
  opacity: 0.95;
}

.stop-icon-button {
  background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
  color: white;
  border: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 15px rgba(34, 197, 94, 0.4);
}

.stop-icon-button:hover {
  background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
  transform: scale(1.05);
  box-shadow: 0 6px 16px rgba(34, 197, 94, 0.45);
}

.stop-icon-button:active {
  transform: scale(0.95);
}

/* 滚动条样式 */
.messages-container::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track {
  background: #1e1e1e;
}

.messages-container::-webkit-scrollbar-thumb {
  background: #3e3e3e;
  border-radius: 4px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: #4e4e4e;
}

/* Bug 保存部分 */
.save-bugs-section {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #2d3a2d;
  border-left: 3px solid #4caf50;
  border-radius: 6px;
}

.save-bugs-button {
  background: #4caf50;
  color: white;
  border: none;
  padding: 8px 14px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.save-bugs-button:hover {
  background: #45a049;
  transform: scale(1.02);
}

.save-bugs-button:active {
  transform: scale(0.98);
}

.bugs-count {
  font-size: 12px;
  color: #aaa;
  margin-left: auto;
}

/* 执行证据部分 */
.evidence-section {
  margin: 12px 0;
  padding: 12px 0;
  border-top: 1px solid #e5e7eb;
}

.reasoning-section {
  margin: 10px 0;
}
.reasoning-details {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafafa;
}
.reasoning-summary {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #6b7280;
  list-style: none;
}
.reasoning-summary::-webkit-details-marker { display: none; }
.reasoning-content {
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.5;
  color: #374151;
  word-break: break-word;
  border-top: 1px solid #e5e7eb;
}
.reasoning-content.reasoning-markdown {
  white-space: normal;
}
.reasoning-markdown p { margin: 0.4em 0; line-height: 1.6; }
.reasoning-markdown p:first-child { margin-top: 0; }
.reasoning-markdown h1, .reasoning-markdown h2, .reasoning-markdown h3 { font-weight: 600; margin: 0.75em 0 0.25em; }
.reasoning-markdown h1 { font-size: 1.2em; }
.reasoning-markdown h2 { font-size: 1.1em; }
.reasoning-markdown h3 { font-size: 1em; }
.reasoning-markdown ul, .reasoning-markdown ol { margin: 0.4em 0; padding-left: 1.5em; }
.reasoning-markdown li { margin: 0.2em 0; }
.reasoning-markdown strong { font-weight: 700; }
.reasoning-markdown code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
.reasoning-markdown pre { background: #f1f5f9; padding: 10px; border-radius: 6px; overflow-x: auto; margin: 0.5em 0; font-size: 0.85em; white-space: pre-wrap; }
.reasoning-markdown pre code { background: none; padding: 0; }

.findings-section {
  margin: 16px 0;
}

.findings-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.findings-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: #f0f9ff;
  border-bottom: 1px solid #bae6fd;
}

.findings-icon {
  font-size: 18px;
}

.findings-title {
  font-size: 14px;
  font-weight: 600;
  color: #0369a1;
  flex: 1;
}

.findings-count {
  font-size: 12px;
  padding: 2px 8px;
  background: #0ea5e9;
  color: #fff;
  border-radius: 12px;
  font-weight: 500;
}

.findings-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.finding-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  line-height: 1.6;
}

.finding-bullet {
  color: #0ea5e9;
  font-size: 16px;
  flex-shrink: 0;
  margin-top: 2px;
}

.finding-text {
  font-size: 14px;
  color: #374151;
}

/* Bug导航列表 */
.bug-navigation-list {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e0e7ff;
}

.bug-nav-header {
  font-size: 13px;
  font-weight: 600;
  color: #4338ca;
  margin-bottom: 8px;
}

.bug-nav-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin: 4px 0;
  background: #f8fafc;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.bug-nav-item:hover {
  background: #e0e7ff;
  transform: translateX(4px);
}

.bug-nav-icon {
  color: #4f46e5;
  margin-right: 8px;
  font-size: 14px;
}

.bug-nav-title {
  color: #1e293b;
  font-size: 14px;
  font-weight: 500;
  flex: 1;
}

.bug-nav-plan {
  color: #64748b;
  font-size: 12px;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
}

/* 修改导航区域 */
.modify-navigation-section {
  margin: 12px 0;
}

.plan-badge {
  background: transparent;
  color: #ffffff;
  font-size: 12px;
  padding: 0;
  border-radius: 0;
  margin-left: 8px;
  font-weight: 600;
  opacity: 0.95;
}

.sandbox-toggle {
  width: 10px;
  height: 10px;
  display: block;
  flex-shrink: 0;
  cursor: pointer;
  /* 让 chevron 图片呈现灰白（深色背景下接近 Qoder 风格） */
  filter: brightness(0) saturate(100%) invert(73%) sepia(11%) saturate(326%) hue-rotate(176deg) brightness(90%) contrast(86%);
  opacity: 0.6;
  transition: opacity 0.15s ease;
}

.sandbox-header:hover .sandbox-toggle {
  opacity: 0.95;
}

.sandbox-toggle.expanded {
  opacity: 0.95;
}

.group-items-hint {
  font-size: 12px;
  color: #888;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #eee;
}

.modify-navigation-content {
  padding: 12px 16px;
}

.modify-field-preview {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  font-size: 14px;
}

.modify-field-preview .field-label {
  color: #6b7280;
  font-weight: 500;
}

.modify-field-preview .old-value {
  color: #ef4444;
  text-decoration: line-through;
  background: #fef2f2;
  padding: 2px 6px;
  border-radius: 4px;
}

.modify-field-preview .old-value.empty-value {
  color: #9ca3af;
  text-decoration: none;
  background: #f3f4f6;
  font-style: italic;
}

.modify-field-preview .arrow {
  color: #9ca3af;
}

.modify-field-preview .new-value {
  color: #059669;
  background: #ecfdf5;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.modify-actions {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e5e7eb;
}

.btn-primary {
  padding: 8px 16px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary:hover {
  background: #2563eb;
}

.btn-secondary {
  padding: 8px 16px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

.btn-icon-approve,
.btn-icon-reject {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  font-size: 18px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-icon-approve {
  background: #10b981;
  color: white;
}

.btn-icon-approve:hover {
  background: #059669;
  transform: scale(1.1);
}

.btn-icon-reject {
  background: #ef4444;
  color: white;
}

.btn-icon-reject:hover {
  background: #dc2626;
  transform: scale(1.1);
}

.evidence-title {
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 12px;
  font-size: 14px;
}

/* 搜索结果部分 */
.search-results-section {
  margin: 12px 0;
  padding: 12px;
  background: #f0f4f8;
  border-left: 3px solid #2196F3;
  border-radius: 4px;
}

.search-results-title {
  font-weight: 600;
  color: #1976D2;
  margin-bottom: 12px;
  font-size: 14px;
}

.search-results-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 500px;
  overflow-y: auto;
}

.search-result-item {
  display: flex;
  gap: 12px;
  padding: 10px;
  background: white;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
  transition: all 0.2s;
}

.search-result-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-color: #2196F3;
}

.search-result-rank {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  background: #2196F3;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 12px;
  margin-top: 2px;
}

.search-result-content {
  flex: 1;
  min-width: 0;
}

.search-result-title {
  font-weight: 600;
  color: #1976D2;
  margin-bottom: 4px;
  font-size: 13px;
  word-break: break-word;
}

.search-result-title:hover {
  color: #1565C0;
  text-decoration: underline;
}

.search-result-url {
  font-size: 11px;
  color: #6b8cae;
  margin-bottom: 6px;
  word-break: break-all;
  font-family: 'Courier New', monospace;
}

.search-result-snippet {
  font-size: 12px;
  color: #555;
  line-height: 1.4;
  word-break: break-word;
}

/* 思考过程样式 - 极简深色风格 */
.reasoning-section {
  margin: 8px 0;
}

.reasoning-details {
  background: transparent; /* 和对话面板融为一体 */
  border: none;
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.2s ease;
}

.reasoning-details[open] {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.22); /* 与待办一致：细边框线包起来 */
}

.reasoning-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: transparent;
  cursor: pointer;
  list-style: none;
  font-size: 12px;
  font-weight: 500;
  color: #ccc;
  user-select: none;
  transition: background 0.2s;
  border-bottom: none; /* 由内容区的 border-top 做分隔，避免双线 */
}

/* 未展开时：不要展示边框线 */
.reasoning-details:not([open]) .reasoning-summary {
  border-bottom: none;
}

/* 行背景保持和对话面板一致：不做 hover/选中变色 */
.reasoning-summary:hover {
  background: transparent;
}

.reasoning-summary::-webkit-details-marker {
  display: none;
}

.reasoning-toggle {
  width: 10px;
  height: 10px;
  display: block;
  flex-shrink: 0;
  margin-left: 6px; /* 在“深度思考”右侧一点 */
  /* 让图标颜色更接近 Qoder 的灰蓝 */
  filter: brightness(0) saturate(100%) invert(73%) sepia(11%) saturate(326%) hue-rotate(176deg) brightness(90%) contrast(86%);
  opacity: 0; /* 默认不显示 */
  transition: opacity 0.15s ease;
  pointer-events: none;
}

/* 两个图标根据 open 状态切换 */
.reasoning-toggle--down { display: none; }

/* 折叠：hover 才显示向右 */
.reasoning-details:not([open]) .reasoning-summary:hover .reasoning-toggle--right {
  opacity: 0.95;
}

/* 展开：常显向下，隐藏向右 */
.reasoning-details[open] .reasoning-toggle--right { display: none; }
.reasoning-details[open] .reasoning-toggle--down {
  display: block;
  opacity: 0.95;
}

.reasoning-icon {
  width: 14px;
  height: 14px;
  display: block;
  filter: invert(1); /* 深色背景下反相成浅色/白色 */
}

.reasoning-title {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
}

/* 旧的倒三角箭头不再使用 */
.reasoning-arrow { display: none; }

.reasoning-content {
  padding: 12px 16px;
  background: transparent; /* 不要深色底，保持轻量 */
  border-top: 1px solid rgba(148, 163, 184, 0.22); /* 标题/内容分隔线 */
  font-size: 13px;
  line-height: 1.6;
  color: #fff;
  overflow-x: auto;
}

.reasoning-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: #cbd5e1; /* Cursor 风格：正文偏灰 */
  animation: reasoningTyping 0.03s steps(1) infinite;
}

.reasoning-text.reasoning-markdown {
  white-space: normal; /* 交给 markdown 的标签排版 */
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'Liberation Sans', sans-serif;
  color: #cbd5e1;
}

/* Cursor 风格：Markdown 分层配色 */
.reasoning-text.reasoning-markdown :deep(p) {
  margin: 0 0 10px;
  line-height: 1.65;
}
.reasoning-text.reasoning-markdown :deep(p:last-child) {
  margin-bottom: 0;
}
.reasoning-text.reasoning-markdown :deep(strong) {
  color: #f8fafc;
  font-weight: 600;
}
.reasoning-text.reasoning-markdown :deep(em) {
  color: #e5e7eb;
}
.reasoning-text.reasoning-markdown :deep(h1),
.reasoning-text.reasoning-markdown :deep(h2),
.reasoning-text.reasoning-markdown :deep(h3) {
  margin: 14px 0 8px;
  color: #f1f5f9;
  font-weight: 600;
  font-size: 13px;
}
.reasoning-text.reasoning-markdown :deep(ul),
.reasoning-text.reasoning-markdown :deep(ol) {
  margin: 8px 0 10px 18px;
  padding: 0;
}
.reasoning-text.reasoning-markdown :deep(li) {
  margin: 4px 0;
}
.reasoning-text.reasoning-markdown :deep(code) {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  color: #e2e8f0;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.18);
  padding: 1px 6px;
  border-radius: 6px;
}
.reasoning-text.reasoning-markdown :deep(pre) {
  margin: 10px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.18);
  overflow: auto;
}
.reasoning-text.reasoning-markdown :deep(pre code) {
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 0;
  color: #e5e7eb;
}
.reasoning-text.reasoning-markdown :deep(a) {
  color: #93c5fd;
  text-decoration: none;
}
.reasoning-text.reasoning-markdown :deep(a:hover) {
  text-decoration: underline;
}

@keyframes reasoningTyping {
  from {
    caret-color: #00ff00;
  }
  to {
    caret-color: transparent;
  }
}

/* 统一总结：Cursor 式「耗时 Xs」+ 打字机，无图标 */
.unified-summary-section {
  margin: 12px 0;
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 6px;
  overflow: hidden;
}
.unified-summary-header {
  padding: 6px 12px;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}
.unified-summary-content.unified-summary-content {
  padding: 12px 16px;
}
.unified-summary-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  color: #fff;
  animation: reasoningTyping 0.03s steps(1) infinite;
}

/* 通用可折叠卡片样式 - 与深度思考一致：深色背景、白色字体（关键发现、沙箱预览、Bug 导航） */
.collapsible-card {
  background: transparent; /* 跟随对话面板底色 */
  border: 1px solid rgba(148, 163, 184, 0.22); /* 细小边框线区分 */
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.2s ease;
  margin-bottom: 12px;
}

.collapsible-card[open] {
  background: transparent;
  border-color: rgba(148, 163, 184, 0.28);
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: transparent;
  cursor: pointer;
  list-style: none;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  user-select: none;
  transition: none;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}

.collapsible-header:hover {
  background: transparent;
}

.collapsible-header::-webkit-details-marker {
  display: none;
}

.card-icon {
  font-size: 14px;
  opacity: 0.8;
}

.card-title {
  flex: 1;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
}

.card-count {
  font-size: 11px;
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 8px;
  border-radius: 10px;
  color: #ccc;
}

.card-arrow {
  font-size: 10px;
  transition: transform 0.2s ease;
  opacity: 0.6;
  color: #888;
}

.collapsible-card[open] .card-arrow {
  transform: rotate(180deg);
}

.sandbox-card .sandbox-header {
  cursor: pointer;
}
.sandbox-card .card-arrow.expanded {
  transform: rotate(180deg);
}

.collapsible-content {
  padding: 12px 16px;
  background: transparent;
  border-top: 1px solid rgba(148, 163, 184, 0.22);
  font-size: 13px;
  line-height: 1.6;
  color: #fff;
  overflow-x: auto;
}

/* 关键发现/沙箱预览/Bug 导航内部内容 - 与深度思考一致的白字深色 */
.collapsible-content .finding-item,
.collapsible-content .finding-text {
  color: #fff;
}
.collapsible-content .finding-bullet {
  color: #888;
}
.collapsible-content .bug-navigation-list {
  border-top-color: rgba(148, 163, 184, 0.22);
}
.collapsible-content .bug-nav-item {
  background: transparent;
  border: 1px solid rgba(148, 163, 184, 0.18);
  color: #fff;
}
.collapsible-content .bug-nav-item:hover {
  background: transparent;
}
.collapsible-content .bug-nav-icon {
  color: #888;
}
.collapsible-content .bug-nav-title {
  color: #fff;
}
.collapsible-content .bug-nav-plan {
  color: #aaa;
  background: rgba(255, 255, 255, 0.08);
}
.collapsible-content .modify-field-preview .field-label {
  color: #ccc;
}
.collapsible-content .modify-field-preview .old-value {
  color: #f87171;
  background: rgba(248, 113, 113, 0.15);
}
.collapsible-content .modify-field-preview .old-value.empty-value {
  color: #888;
  background: transparent;
}
.collapsible-content .modify-field-preview .arrow {
  color: #666;
}
.collapsible-content .modify-field-preview .new-value {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.15);
}
.collapsible-content .modify-actions {
  border-top-color: rgba(148, 163, 184, 0.22);
}
.collapsible-content .group-items-hint {
  color: #aaa;
}
.collapsible-content .btn-primary {
  background: #333;
  color: #fff;
  border: 1px solid #444;
}
.collapsible-content .btn-primary:hover {
  background: #444;
}

.model-select-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
}

.model-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  flex-shrink: 0;
}

.model-icon--ernie {
  width: 16px;
  height: 16px;
}
</style>
