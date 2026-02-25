<template>
  <div class="step-timeline">
    <div v-for="(step, index) in steps" :key="index" class="timeline-item">
      <!-- 进度连接线 -->
      <div v-if="index < steps.length - 1" class="timeline-connector"></div>

      <!-- 状态指示器 -->
      <div class="timeline-node" :class="step.status">
        <span class="node-icon">{{ getIcon(step.status) }}</span>
      </div>

      <!-- 步骤内容 -->
      <div class="timeline-content">
        <div class="step-header">
          <h4 class="step-title">{{ step.title }}</h4>
          <span v-if="step.duration" class="step-duration">{{ formatDuration(step.duration) }}</span>
        </div>
        <p v-if="step.description" class="step-description">{{ step.description }}</p>

        <!-- 工具调用信息 -->
        <div v-if="step.toolCall" class="tool-call">
          <div class="tool-info">
            <span class="tool-label">🔧 工具:</span>
            <span class="tool-name">{{ step.toolCall.name }}</span>
          </div>
          <div v-if="step.toolCall.output" class="tool-output">
            <pre>{{ step.toolCall.output }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 总体进度条 -->
    <div v-if="totalSteps > 0" class="progress-summary">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercentage + '%' }"></div>
      </div>
      <div class="progress-text">
        进度: {{ completedSteps }} / {{ totalSteps }} 步
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  steps: {
    type: Array,
    default: () => []
  }
})

const getIcon = (status) => {
  const icons = {
    pending: '⏳',
    running: '▶️',
    completed: '✅',
    error: '❌'
  }
  return icons[status] || '•'
}

const formatDuration = (ms) => {
  if (typeof ms !== 'number') return ''
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${ms}ms`
}

const totalSteps = computed(() => props.steps.length)

const completedSteps = computed(() => {
  return props.steps.filter(s => s.status === 'completed' || s.status === 'error').length
})

const progressPercentage = computed(() => {
  if (totalSteps.value === 0) return 0
  return Math.round((completedSteps.value / totalSteps.value) * 100)
})
</script>

<style scoped>
.step-timeline {
  position: relative;
  padding: 20px 0;
}

.timeline-item {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
  position: relative;
}

.timeline-connector {
  position: absolute;
  left: 20px;
  top: 50px;
  width: 2px;
  height: calc(100% + 24px);
  background: linear-gradient(to bottom, #3b82f6, #10b981);
  opacity: 0.3;
}

.timeline-node {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  position: relative;
  z-index: 1;
  background: white;
  border: 2px solid #e5e7eb;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
  transition: all 0.3s ease;
}

.timeline-node.pending {
  border-color: #9ca3af;
  background: #f3f4f6;
}

.timeline-node.running {
  border-color: #3b82f6;
  background: #dbeafe;
  animation: pulse-border 1.5s infinite;
}

.timeline-node.completed {
  border-color: #10b981;
  background: #dcfce7;
}

.timeline-node.error {
  border-color: #ef4444;
  background: #fee2e2;
}

@keyframes pulse-border {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(59, 130, 246, 0);
  }
}

.timeline-content {
  flex: 1;
  padding: 12px 16px;
  background: #f9fafb;
  border-radius: 8px;
  border-left: 3px solid #3b82f6;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.step-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.step-duration {
  background: #fef08a;
  color: #92400e;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

.step-description {
  margin: 0;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
}

.tool-call {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e5e7eb;
}

.tool-info {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.tool-label {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
}

.tool-name {
  background: #ede9fe;
  color: #6d28d9;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 500;
}

.tool-output {
  background: #1f2937;
  color: #10b981;
  padding: 8px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 11px;
  max-height: 120px;
  overflow-y: auto;
}

.tool-output pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 进度条 */
.progress-summary {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 2px solid #e5e7eb;
}

.progress-bar {
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #10b981);
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 12px;
  color: #6b7280;
  text-align: right;
  font-weight: 500;
}

/* 响应式 */
@media (max-width: 768px) {
  .timeline-item {
    gap: 12px;
  }

  .timeline-node {
    width: 32px;
    height: 32px;
    font-size: 14px;
  }

  .timeline-content {
    padding: 10px 12px;
  }

  .step-title {
    font-size: 13px;
  }

  .step-duration {
    font-size: 11px;
  }
}
</style>
