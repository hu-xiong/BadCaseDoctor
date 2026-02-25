<template>
  <div class="evidence-card">
    <!-- 工具链路头部 -->
    <div class="evidence-header">
      <div class="tool-chain">
        <span class="tool-icon">🔧</span>
        <span class="tool-name">{{ evidence.tool_used }}</span>
        <span v-if="evidence.url_accessed" class="url-badge">
          🌐 {{ formatUrl(evidence.url_accessed) }}
        </span>
      </div>
      <div class="execution-meta">
        <span v-if="evidence.execution_time_ms" class="time-badge">
          ⏱️ {{ formatTime(evidence.execution_time_ms) }}
        </span>
        <span class="status-badge" :class="evidence.status">
          {{ statusText }}
        </span>
      </div>
    </div>

    <!-- 工具参数 -->
    <div v-if="evidence.tool_params && Object.keys(evidence.tool_params).length > 0" class="params-section">
      <div class="section-title">⚙️ 工具参数</div>
      <div class="params-list">
        <div v-for="(value, key) in evidence.tool_params" :key="key" class="param-item">
          <span class="param-key">{{ key }}:</span>
          <span class="param-value">{{ formatParamValue(value) }}</span>
        </div>
      </div>
    </div>

    <!-- 执行结果 -->
    <div v-if="evidence.results && evidence.results.length > 0" class="results-section">
      <div class="section-title">📊 执行结果 ({{ evidence.results.length }} 项)</div>
      <div class="results-list">
        <div v-for="(result, index) in displayResults" :key="index" class="result-item">
          <span class="result-index">{{ index + 1 }}.</span>
          <span class="result-text">{{ result }}</span>
        </div>
        <div v-if="evidence.results.length > maxDisplayResults" class="show-more">
          + {{ evidence.results.length - maxDisplayResults }} 项结果
        </div>
      </div>
    </div>

    <!-- 动画指示 -->
    <div v-if="isAnimating" class="executing-indicator">
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
      执行中...
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  evidence: {
    type: Object,
    required: true
  },
  isAnimating: {
    type: Boolean,
    default: false
  },
  maxDisplayResults: {
    type: Number,
    default: 5
  }
})

const formatUrl = (url) => {
  try {
    const urlObj = new URL(url)
    return urlObj.pathname + (urlObj.hash || '')
  } catch {
    return url.substring(0, 40) + (url.length > 40 ? '...' : '')
  }
}

const formatTime = (ms) => {
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(2)}s`
  }
  return `${ms}ms`
}

const formatParamValue = (value) => {
  if (typeof value === 'string') return value
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const displayResults = computed(() => {
  if (!props.evidence.results) return []
  return props.evidence.results.slice(0, props.maxDisplayResults)
})

const statusText = computed(() => {
  if (props.evidence.status === 'success') return '✅ 成功'
  if (props.evidence.status === 'failure') return '❌ 失败'
  return '⏳ 执行中'
})
</script>

<style scoped>
.evidence-card {
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  border: 1px solid #d0d7e3;
  border-radius: 8px;
  padding: 12px 16px;
  margin: 8px 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.evidence-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.evidence-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.tool-chain {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.tool-icon {
  font-size: 16px;
}

.tool-name {
  font-weight: 600;
  color: #1f2937;
  font-size: 14px;
}

.url-badge {
  background: #dbeafe;
  color: #0369a1;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

.execution-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}

.time-badge {
  background: #fef08a;
  color: #92400e;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.status-badge.success {
  background: #dcfce7;
  color: #166534;
}

.status-badge.failure {
  background: #fee2e2;
  color: #991b1b;
}

.status-badge.unknown {
  background: #e5e7eb;
  color: #374151;
}

.params-section,
.results-section {
  margin-top: 12px;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #4b5563;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.params-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 8px;
}

.param-item {
  background: rgba(255, 255, 255, 0.7);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  border-left: 2px solid #3b82f6;
}

.param-key {
  font-weight: 600;
  color: #1f2937;
  margin-right: 4px;
}

.param-value {
  color: #6b7280;
  word-break: break-all;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.result-item {
  background: rgba(255, 255, 255, 0.7);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  display: flex;
  gap: 8px;
  border-left: 2px solid #10b981;
}

.result-index {
  color: #6b7280;
  font-weight: 600;
  min-width: 20px;
}

.result-text {
  color: #1f2937;
  flex: 1;
  word-break: break-word;
}

.show-more {
  color: #6b7280;
  font-size: 12px;
  font-style: italic;
  padding: 8px;
  text-align: center;
}

.executing-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 12px;
  color: #3b82f6;
  font-size: 12px;
  animation: pulse 1.5s infinite;
}

.dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  animation: bounce 1.4s infinite;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .evidence-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .params-list {
    grid-template-columns: 1fr;
  }

  .results-list {
    max-height: 150px;
  }
}
</style>
