<template>
  <div class="execution-result">
    <ol class="exec-steps">
      <li v-for="(result, index) in results" :key="index" class="exec-step">
        <div class="exec-step-title">
          <strong>步骤 {{ index + 1 }}</strong>
          <span v-if="result.success !== undefined" class="exec-step-status" :class="getStatusClass(result)">
            {{ getStatusText(result) }}
          </span>
        </div>
        <div class="exec-step-body markdown-body" v-html="renderMarkdown(result.text || '')"></div>
      </li>
    </ol>

    <div v-if="isLoading" class="loading-indicator" aria-label="loading">
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    </div>
  </div>
</template>

<script setup>
import { marked } from 'marked'

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

const renderMarkdown = (text) => {
  try {
    return marked.parse(String(text || ''), { breaks: true })
  } catch {
    return String(text || '')
  }
}

const getStatusText = (result) => {
  if (result.success === false) return '失败'
  if (result.success === true) return '成功'
  return '完成'
}

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
  padding: 8px 0 0;
}

.exec-steps {
  margin: 0;
  padding-left: 18px;
}

.exec-step {
  padding: 10px 0;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
}

.exec-step:first-child {
  border-top: none;
}

.exec-step-title {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #ffffff;
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 6px;
}

.exec-step-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  color: rgba(229, 231, 235, 0.95);
  opacity: 0.95;
}

.status-success {
  border-color: rgba(74, 222, 128, 0.35);
  color: rgba(187, 247, 208, 0.95);
}

.status-error {
  border-color: rgba(248, 113, 113, 0.4);
  color: rgba(254, 202, 202, 0.95);
}

.status-complete {
  border-color: rgba(147, 197, 253, 0.35);
  color: rgba(219, 234, 254, 0.95);
}

.exec-step-body {
  color: rgba(229, 231, 235, 0.95);
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.loading-indicator {
  display: flex;
  gap: 6px;
  justify-content: center;
  padding: 12px 0;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(148, 163, 184, 0.55);
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
  0%,
  60%,
  100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  30% {
    transform: scale(1.2);
    opacity: 1;
  }
}

/* 简单 markdown（白字） */
.markdown-body :deep(p) {
  margin: 0.35em 0;
}
.markdown-body :deep(pre) {
  margin: 0.5em 0;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  background: transparent;
  overflow: auto;
  color: rgba(229, 231, 235, 0.95);
  white-space: pre-wrap;
}
.markdown-body :deep(code) {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 6px;
  padding: 1px 6px;
  background: transparent;
  color: rgba(229, 231, 235, 0.95);
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.35em 0;
  padding-left: 1.25em;
}
.markdown-body :deep(li) {
  margin: 0.15em 0;
}
</style>
