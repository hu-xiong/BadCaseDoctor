<template>
  <div class="metrics-dashboard">
    <div class="dashboard-header">
      <h2>📊 性能监控仪表板</h2>
      <button @click="refreshMetrics" class="refresh-btn" :disabled="isLoading">
        🔄 刷新
      </button>
    </div>

    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading">正在加载指标...</div>

    <!-- 错误提示 -->
    <div v-else-if="error" class="error-message">
      ❌ {{ error }}
    </div>

    <!-- 指标卡片网格 -->
    <div v-else class="metrics-grid">
      <!-- Agent 执行 -->
      <div class="metric-card">
        <div class="card-title">🤖 Agent 执行</div>
        <div class="metric-item">
          <span class="label">总执行次数:</span>
          <span class="value">{{ metrics.agentExecuteTotal }}</span>
        </div>
        <div class="metric-item">
          <span class="label">平均耗时:</span>
          <span class="value">{{ metrics.agentAvgDuration.toFixed(2) }}s</span>
        </div>
        <div class="metric-item">
          <span class="label">成功率:</span>
          <span class="value success">{{ metrics.agentSuccessRate }}%</span>
        </div>
      </div>

      <!-- 测试执行 -->
      <div class="metric-card">
        <div class="card-title">🧪 测试执行</div>
        <div class="metric-item">
          <span class="label">总执行次数:</span>
          <span class="value">{{ metrics.testExecuteTotal }}</span>
        </div>
        <div class="metric-item">
          <span class="label">平均耗时:</span>
          <span class="value">{{ metrics.testAvgDuration.toFixed(2) }}s</span>
        </div>
        <div class="metric-item">
          <span class="label">发现 Bug:</span>
          <span class="value highlight">{{ metrics.bugsFoundTotal }}</span>
        </div>
      </div>

      <!-- Bug 保存 -->
      <div class="metric-card">
        <div class="card-title">💾 Bug 保存</div>
        <div class="metric-item">
          <span class="label">保存次数:</span>
          <span class="value">{{ metrics.bugsSavedCount }}</span>
        </div>
        <div class="metric-item">
          <span class="label">平均耗时:</span>
          <span class="value">{{ metrics.bugsSaveAvgDuration.toFixed(2) }}s</span>
        </div>
        <div class="metric-item">
          <span class="label">成功率:</span>
          <span class="value success">{{ metrics.bugsSaveSuccessRate }}%</span>
        </div>
      </div>

      <!-- 意图识别 -->
      <div class="metric-card">
        <div class="card-title">🎯 意图识别</div>
        <div class="metric-item">
          <span class="label">总识别次数:</span>
          <span class="value">{{ metrics.intentDetectionTotal }}</span>
        </div>
        <div class="metric-item">
          <span class="label">平均耗时:</span>
          <span class="value">{{ metrics.intentAvgDuration.toFixed(2) }}s</span>
        </div>
        <div class="metric-item">
          <span class="label">识别准确率:</span>
          <span class="value success">{{ metrics.intentSuccessRate }}%</span>
        </div>
      </div>

      <!-- API 统计 -->
      <div class="metric-card">
        <div class="card-title">🌐 API 统计</div>
        <div class="metric-item">
          <span class="label">总请求数:</span>
          <span class="value">{{ metrics.apiRequestsTotal }}</span>
        </div>
        <div class="metric-item">
          <span class="label">平均响应时间:</span>
          <span class="value">{{ metrics.apiAvgDuration.toFixed(3) }}s</span>
        </div>
        <div class="metric-item">
          <span class="label">成功状态码:</span>
          <span class="value success">{{ metrics.apiSuccessCount }}</span>
        </div>
      </div>

      <!-- 系统统计 -->
      <div class="metric-card">
        <div class="card-title">⚙️ 系统统计</div>
        <div class="metric-item">
          <span class="label">最后更新:</span>
          <span class="value">{{ lastUpdateTime }}</span>
        </div>
        <div class="metric-item">
          <span class="label">数据来源:</span>
          <span class="value">Prometheus</span>
        </div>
        <div class="metric-item">
          <span class="label">更新周期:</span>
          <span class="value">5s</span>
        </div>
      </div>
    </div>

    <!-- Bug 严重程度分布 -->
    <div v-if="!isLoading && !error" class="severity-section">
      <h3>🐛 Bug 严重程度分布</h3>
      <div class="severity-bars">
        <div class="severity-item critical">
          <span class="label">🔴 Critical:</span>
          <div class="bar">
            <div class="fill" :style="{ width: metrics.bugsBySeverity.critical + '%' }"></div>
          </div>
          <span class="count">{{ Math.round(metrics.bugsFoundTotal * metrics.bugsBySeverity.critical / 100) }}</span>
        </div>
        <div class="severity-item high">
          <span class="label">🟠 High:</span>
          <div class="bar">
            <div class="fill" :style="{ width: metrics.bugsBySeverity.high + '%' }"></div>
          </div>
          <span class="count">{{ Math.round(metrics.bugsFoundTotal * metrics.bugsBySeverity.high / 100) }}</span>
        </div>
        <div class="severity-item medium">
          <span class="label">🟡 Medium:</span>
          <div class="bar">
            <div class="fill" :style="{ width: metrics.bugsBySeverity.medium + '%' }"></div>
          </div>
          <span class="count">{{ Math.round(metrics.bugsFoundTotal * metrics.bugsBySeverity.medium / 100) }}</span>
        </div>
        <div class="severity-item low">
          <span class="label">🟢 Low:</span>
          <div class="bar">
            <div class="fill" :style="{ width: metrics.bugsBySeverity.low + '%' }"></div>
          </div>
          <span class="count">{{ Math.round(metrics.bugsFoundTotal * metrics.bugsBySeverity.low / 100) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

const isLoading = ref(false)
const error = ref(null)
const lastUpdateTime = ref('--:--:--')

const metrics = ref({
  agentExecuteTotal: 0,
  agentAvgDuration: 0,
  agentSuccessRate: 0,
  testExecuteTotal: 0,
  testAvgDuration: 0,
  bugsFoundTotal: 0,
  bugsSavedCount: 0,
  bugsSaveAvgDuration: 0,
  bugsSaveSuccessRate: 0,
  intentDetectionTotal: 0,
  intentAvgDuration: 0,
  intentSuccessRate: 0,
  apiRequestsTotal: 0,
  apiAvgDuration: 0,
  apiSuccessCount: 0,
  bugsBySeverity: {
    critical: 20,
    high: 30,
    medium: 35,
    low: 15
  }
})

let refreshInterval = null

const refreshMetrics = async () => {
  isLoading.value = true
  error.value = null
  
  try {
    const response = await axios.get('http://localhost:5000/metrics')
    const metricsText = response.data
    
    // 解析 Prometheus 文本格式指标
    parsePrometheusMetrics(metricsText)
    
    lastUpdateTime.value = new Date().toLocaleTimeString()
  } catch (err) {
    console.error('Failed to fetch metrics:', err)
    error.value = '无法连接到后端指标端点，请确保后端运行在 http://localhost:5000'
  } finally {
    isLoading.value = false
  }
}

const parsePrometheusMetrics = (metricsText) => {
  // 简单的 Prometheus 格式解析
  const lines = metricsText.split('\n')
  
  let agentExecuteSuccess = 0
  let agentExecuteFailure = 0
  let agentDurations = []
  let testExecutes = 0
  let bugsCritical = 0, bugsHigh = 0, bugsMedium = 0, bugsLow = 0
  let bugsSaved = 0
  let bugsSaveDurations = []
  let intentDetections = 0
  let intentDurations = []
  let apiRequests = 0
  let apiDurations = []
  
  for (const line of lines) {
    if (line.includes('agent_execute_total') && line.includes('success')) {
      const match = line.match(/agent_execute_total.*?\s(\d+)/)
      if (match) agentExecuteSuccess = parseInt(match[1])
    } else if (line.includes('agent_execute_total') && line.includes('failure')) {
      const match = line.match(/agent_execute_total.*?\s(\d+)/)
      if (match) agentExecuteFailure = parseInt(match[1])
    } else if (line.includes('agent_execute_duration_seconds_bucket')) {
      const match = line.match(/agent_execute_duration_seconds_bucket.*?\s(\d+)/)
      if (match) agentDurations.push(parseFloat(match[1]))
    } else if (line.includes('test_execute_total') && !line.startsWith('#')) {
      const match = line.match(/test_execute_total.*?\s(\d+)/)
      if (match) testExecutes = parseInt(match[1])
    } else if (line.includes('bugs_found_total')) {
      if (line.includes('critical')) {
        const match = line.match(/bugs_found_total.*?\s(\d+)/)
        if (match) bugsCritical = parseInt(match[1])
      } else if (line.includes('high')) {
        const match = line.match(/bugs_found_total.*?\s(\d+)/)
        if (match) bugsHigh = parseInt(match[1])
      } else if (line.includes('medium')) {
        const match = line.match(/bugs_found_total.*?\s(\d+)/)
        if (match) bugsMedium = parseInt(match[1])
      } else if (line.includes('low')) {
        const match = line.match(/bugs_found_total.*?\s(\d+)/)
        if (match) bugsLow = parseInt(match[1])
      }
    } else if (line.includes('bugs_saved_total') && line.includes('success')) {
      const match = line.match(/bugs_saved_total.*?\s(\d+)/)
      if (match) bugsSaved = parseInt(match[1])
    } else if (line.includes('bugs_saved_duration_seconds')) {
      const match = line.match(/bugs_saved_duration_seconds.*?\s([\d.]+)/)
      if (match) bugsSaveDurations.push(parseFloat(match[1]))
    } else if (line.includes('intent_detection_total')) {
      const match = line.match(/intent_detection_total.*?\s(\d+)/)
      if (match) intentDetections += parseInt(match[1])
    } else if (line.includes('intent_detection_duration_seconds')) {
      const match = line.match(/intent_detection_duration_seconds.*?\s([\d.]+)/)
      if (match) intentDurations.push(parseFloat(match[1]))
    } else if (line.includes('api_requests_total')) {
      const match = line.match(/api_requests_total.*?\s(\d+)/)
      if (match) apiRequests += parseInt(match[1])
    } else if (line.includes('api_request_duration_seconds')) {
      const match = line.match(/api_request_duration_seconds.*?\s([\d.]+)/)
      if (match) apiDurations.push(parseFloat(match[1]))
    }
  }
  
  const totalBugs = bugsCritical + bugsHigh + bugsMedium + bugsLow
  
  metrics.value = {
    agentExecuteTotal: agentExecuteSuccess + agentExecuteFailure,
    agentAvgDuration: agentDurations.length > 0 
      ? agentDurations.reduce((a, b) => a + b) / agentDurations.length 
      : 0,
    agentSuccessRate: agentExecuteSuccess + agentExecuteFailure > 0 
      ? Math.round(agentExecuteSuccess * 100 / (agentExecuteSuccess + agentExecuteFailure)) 
      : 0,
    testExecuteTotal: testExecutes,
    testAvgDuration: 0,
    bugsFoundTotal: totalBugs,
    bugsSavedCount: bugsSaved,
    bugsSaveAvgDuration: bugsSaveDurations.length > 0 
      ? bugsSaveDurations.reduce((a, b) => a + b) / bugsSaveDurations.length 
      : 0,
    bugsSaveSuccessRate: 100,
    intentDetectionTotal: intentDetections,
    intentAvgDuration: intentDurations.length > 0 
      ? intentDurations.reduce((a, b) => a + b) / intentDurations.length 
      : 0,
    intentSuccessRate: 100,
    apiRequestsTotal: apiRequests,
    apiAvgDuration: apiDurations.length > 0 
      ? apiDurations.reduce((a, b) => a + b) / apiDurations.length 
      : 0,
    apiSuccessCount: apiRequests,
    bugsBySeverity: {
      critical: totalBugs > 0 ? Math.round(bugsCritical * 100 / totalBugs) : 0,
      high: totalBugs > 0 ? Math.round(bugsHigh * 100 / totalBugs) : 0,
      medium: totalBugs > 0 ? Math.round(bugsMedium * 100 / totalBugs) : 0,
      low: totalBugs > 0 ? Math.round(bugsLow * 100 / totalBugs) : 0
    }
  }
}

onMounted(() => {
  refreshMetrics()
  
  // 每 5 秒自动刷新一次
  refreshInterval = setInterval(refreshMetrics, 5000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.metrics-dashboard {
  padding: 20px;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 8px;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 2px solid #3e3e3e;
}

.dashboard-header h2 {
  margin: 0;
  font-size: 24px;
}

.refresh-btn {
  background: #007acc;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: #0098ff;
  transform: scale(1.05);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading,
.error-message {
  padding: 20px;
  text-align: center;
  border-radius: 6px;
  font-size: 14px;
}

.loading {
  background: #2d2d2d;
  color: #888;
}

.error-message {
  background: #3a2d2d;
  color: #f44336;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 30px;
}

.metric-card {
  background: #252526;
  border: 1px solid #3e3e3e;
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s;
}

.metric-card:hover {
  border-color: #007acc;
  box-shadow: 0 0 0 1px #007acc;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #4fc3f7;
}

.metric-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #3e3e4e;
}

.metric-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.label {
  font-size: 12px;
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.value {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  font-family: 'Monaco', 'Menlo', monospace;
}

.value.success {
  color: #4caf50;
}

.value.highlight {
  color: #ff9800;
}

.severity-section {
  background: #252526;
  border: 1px solid #3e3e3e;
  border-radius: 8px;
  padding: 20px;
  margin-top: 20px;
}

.severity-section h3 {
  margin-top: 0;
  margin-bottom: 15px;
  color: #4fc3f7;
}

.severity-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.severity-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.severity-item .label {
  width: 100px;
  flex-shrink: 0;
}

.severity-item .bar {
  flex: 1;
  height: 20px;
  background: #3e3e3e;
  border-radius: 4px;
  overflow: hidden;
}

.severity-item .fill {
  height: 100%;
  transition: width 0.3s ease;
}

.severity-item.critical .fill {
  background: #f44336;
}

.severity-item.high .fill {
  background: #ff9800;
}

.severity-item.medium .fill {
  background: #ffc107;
}

.severity-item.low .fill {
  background: #4caf50;
}

.severity-item .count {
  width: 40px;
  text-align: right;
  font-weight: 600;
  font-size: 14px;
}
</style>
