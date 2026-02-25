<template>
  <div class="execution-result">
    <!-- 执行步骤结果 - 可折叠 -->
    <div 
      v-for="(result, index) in results" 
      :key="index"
      class="result-card"
    >
      <!-- 卡片头部 - 可点击折叠 -->
      <div 
        class="result-header"
        @click="toggleExpand(index)"
      >
        <div class="header-left">
          <span class="expand-icon" :class="{ expanded: expandedItems[index] }">
            ▶
          </span>
          <span class="result-step">Step {{ index + 1 }}</span>
          <span class="result-preview">{{ getPreview(result.text) }}</span>
        </div>
        <div class="header-right">
          <span class="result-status" :class="getStatusClass(result)">
            {{ getStatusText(result) }}
          </span>
        </div>
      </div>
      
      <!-- 卡片内容 - 可展开/折叠 -->
      <transition name="expand">
        <div v-if="expandedItems[index]" class="result-content">
          <!-- 历史消息一次性渲染，新消息打字机效果 -->
          <div v-if="instant" class="result-text">{{ result.text }}</div>
          <TypewriterText 
            v-else
            :text="result.text"
            :speed="20"
            :autoPlay="true"
          />
        </div>
      </transition>
    </div>

    <!-- 加载中指示 -->
    <div v-if="isLoading" class="loading-indicator">
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import TypewriterText from './TypewriterText.vue'

const props = defineProps({
  results: {
    type: Array,
    default: () => []
  },
  isLoading: {
    type: Boolean,
    default: false
  },
  instant: {
    type: Boolean,
    default: false
  }
})

// 折叠状态（默认第一个展开）
const expandedItems = ref({})
props.results.forEach((_, index) => {
  expandedItems.value[index] = index === 0 // 只展开第一个
})

// 切换折叠
const toggleExpand = (index) => {
  expandedItems.value[index] = !expandedItems.value[index]
}

// 获取预览文本
const getPreview = (text) => {
  if (!text) return ''
  return text.length > 50 ? text.substring(0, 50) + '...' : text
}

// 获取状态文本
const getStatusText = (result) => {
  if (result.success === false) return '失败'
  if (result.success === true) return '成功'
  return '完成'
}

// 获取状态样式
const getStatusClass = (result) => {
  if (result.success === false) return 'status-error'
  if (result.success === true) return 'status-success'
  return 'status-complete'
}
</script>

<style scoped>
.execution-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}

.result-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  transition: all 0.2s ease;
}

.result-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
  background: #f9fafb;
  transition: background 0.2s ease;
}

.result-header:hover {
  background: #f3f4f6;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.expand-icon {
  font-size: 10px;
  color: #6b7280;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.result-step {
  font-size: 12px;
  font-weight: 600;
  color: #3b82f6;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  flex-shrink: 0;
}

.result-preview {
  font-size: 13px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-right {
  flex-shrink: 0;
}

.result-status {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 12px;
  font-weight: 500;
}

.status-success {
  background: #d1fae5;
  color: #065f46;
}

.status-error {
  background: #fee2e2;
  color: #991b1b;
}

.status-complete {
  background: #dbeafe;
  color: #1e40af;
}

.result-content {
  padding: 16px;
  background: #fff;
  border-top: 1px solid #e5e7eb;
  font-size: 13px;
  line-height: 1.6;
  color: #374151;
}

.result-text {
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* 折叠动画 */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  max-height: 500px;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
}

.loading-indicator {
  display: flex;
  gap: 4px;
  padding: 8px 0;
}

.dot {
  width: 6px;
  height: 6px;
  background: #3b82f6;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.dot:nth-child(1) {
  animation-delay: 0s;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes bounce {
  0%, 60%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  30% {
    transform: scale(1.2);
    opacity: 1;
  }
}
</style>
