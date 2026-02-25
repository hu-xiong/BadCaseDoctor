<template>
  <div class="qoder-todo-list">
    <div v-for="(todo, index) in todos" :key="index" class="qoder-todo-item">
      <div class="qoder-todo-icon"></div>
      <div v-if="index < todos.length - 1" class="qoder-todo-line"></div>
      <div class="qoder-todo-content-wrapper">
        <!-- 步骤头部：工具名称 + 结果摘要 -->
        <div class="qoder-todo-header" @click="toggleExpand(index)">
          <div class="header-content">
            <div class="qoder-todo-text">{{ todo.text }}</div>
            <div v-if="todo.resultSummary" class="qoder-todo-result">{{ todo.resultSummary }}</div>
            <!-- loading动画（步骤running时） -->
            <span v-if="todo.status === 'running'" class="loading-dots">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </span>
          </div>
          <span v-if="hasExpandableContent(todo)" class="expand-icon" :class="{ expanded: expandedItems[index] }">▶</span>
        </div>
        
        <!-- 工具执行输出 + evidence卡片 -->
        <transition name="expand">
          <div v-if="expandedItems[index] && hasExpandableContent(todo)" class="qoder-todo-details">
            <!-- Evidence卡片显示 -->
            <div v-if="todo.evidence" class="evidence-card">
              <div class="evidence-header">
                <span class="evidence-icon">📊</span>
                <span class="evidence-title">执行证据</span>
              </div>
              <div class="evidence-content">
                <pre>{{ formatEvidence(todo.evidence) }}</pre>
              </div>
            </div>
            
            <!-- 原始输出（如果evidence不存在） -->
            <div v-else-if="todo.toolCall && todo.toolCall.output" class="qoder-todo-output">
              <pre>{{ formatOutput(todo.toolCall.output) }}</pre>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  todos: {
    type: Array,
    default: () => []
  }
})

const expandedItems = ref({})

const toggleExpand = (index) => {
  expandedItems.value[index] = !expandedItems.value[index]
}

// 判断是否有可展开内容
const hasExpandableContent = (todo) => {
  return todo.evidence || (todo.toolCall && todo.toolCall.output)
}

// 格式化evidence
const formatEvidence = (evidence) => {
  if (typeof evidence === 'string') {
    try {
      const parsed = JSON.parse(evidence)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return evidence
    }
  }
  return JSON.stringify(evidence, null, 2)
}

const formatOutput = (output) => {
  if (typeof output === 'string') {
    try {
      const parsed = JSON.parse(output)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return output
    }
  }
  return JSON.stringify(output, null, 2)
}
</script>

<style scoped>
.qoder-todo-list {
  position: relative;
  padding: 8px 0;
}

.qoder-todo-item {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
  align-items: flex-start;
}

.qoder-todo-icon {
  width: 36px;
  height: 36px;
  background: #3b82f6;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.qoder-todo-icon::after {
  content: '▶';
  color: white;
  font-size: 14px;
}

.qoder-todo-line {
  position: absolute;
  width: 2px;
  background: #d1d5db;
  left: 17px;
  top: 44px;
  height: 20px;
}

.qoder-todo-item:last-child .qoder-todo-line {
  display: none;
}

.qoder-todo-content-wrapper {
  flex: 1;
  min-width: 0;
}

.qoder-todo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #374151;
  color: #e5e7eb;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.5;
  cursor: pointer;
  transition: background 0.2s;
}

.qoder-todo-header:hover {
  background: #4b5563;
}

.header-content {
  flex: 1;
  min-width: 0;
}

.qoder-todo-text {
  font-weight: 500;
  margin-bottom: 4px;
  word-wrap: break-word;
}

.qoder-todo-result {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 4px;
}

/* loading动画（步骤执行中） */
.loading-dots {
  display: inline-flex;
  gap: 4px;
  margin-left: 8px;
  align-items: center;
}

.loading-dots .dot {
  width: 4px;
  height: 4px;
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

.expand-icon {
  font-size: 10px;
  color: #9ca3af;
  transition: transform 0.2s;
  margin-left: 8px;
  flex-shrink: 0;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.qoder-todo-details {
  margin-top: 8px;
}

/* Evidence卡片样式 */
.evidence-card {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  overflow: hidden;
}

.evidence-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #e0f2fe;
  border-bottom: 1px solid #bae6fd;
}

.evidence-icon {
  font-size: 16px;
}

.evidence-title {
  font-size: 13px;
  font-weight: 600;
  color: #0369a1;
}

.evidence-content {
  padding: 12px;
}

.evidence-content pre {
  margin: 0;
  color: #1e293b;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
}

/* 原始输出样式 */
.qoder-todo-output {
  background: #1f2937;
  border-radius: 6px;
  padding: 12px;
  max-height: 400px;
  overflow: auto;
}

.qoder-todo-output pre {
  margin: 0;
  color: #d1d5db;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Courier New', monospace;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
  max-height: 400px;
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
}
</style>
