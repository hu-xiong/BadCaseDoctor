<template>
  <div class="streaming-message">
    <!-- 理解信息段 -->
    <div v-if="isShowingUnderstanding" class="understanding-section">
      <div class="section-icon">🧠</div>
      <TypewriterText 
        :text="understandingText"
        :speed="20"
        :autoPlay="true"
      />
    </div>

    <!-- 步骤展示 -->
    <div v-for="(step, idx) in displaySteps" :key="idx" class="step-section">
      <div class="step-marker">Step {{ idx + 1 }}</div>
      
      <!-- 步骤标题 - 打字机效果 -->
      <div v-if="step.showTitle" class="step-title-wrapper">
        <TypewriterText 
          :text="step.title"
          :speed="25"
          :autoPlay="true"
        />
      </div>

      <!-- 步骤描述 - 打字机效果 -->
      <div v-if="step.showDescription && step.description" class="step-description-wrapper">
        <TypewriterText 
          :text="step.description"
          :speed="15"
          :autoPlay="true"
        />
      </div>

      <!-- 步骤问题/子步骤 -->
      <div v-if="step.substeps && step.substeps.length > 0" class="substeps-list">
        <div v-for="(substep, sidx) in step.substeps" :key="sidx" class="substep-item">
          <span class="substep-icon">→</span>
          <TypewriterText 
            :text="substep"
            :speed="15"
            :autoPlay="true"
          />
        </div>
      </div>

      <!-- 步骤执行状态 -->
      <div v-if="step.executing" class="step-executing">
        <span class="executing-dot"></span>
        执行中...
      </div>

      <div v-else-if="step.completed" class="step-completed">
        ✅ 已完成
      </div>
    </div>

    <!-- 加载指示 -->
    <div v-if="isLoading" class="loading-indicator">
      <span class="loader"></span>
      正在处理...
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import TypewriterText from './TypewriterText.vue'

const props = defineProps({
  understanding: {
    type: String,
    default: ''
  },
  steps: {
    type: Array,
    default: () => []
  },
  isLoading: {
    type: Boolean,
    default: false
  }
})

const isShowingUnderstanding = computed(() => !!props.understanding)

const understandingText = computed(() => {
  return props.understanding || ''
})

const displaySteps = computed(() => {
  return props.steps.map((step, idx) => ({
    ...step,
    showTitle: true,
    showDescription: !!step.description,
    executing: step.status === 'running',
    completed: step.status === 'completed' || step.status === 'error'
  }))
})
</script>

<style scoped>
.streaming-message {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  color: #1f2937;
}

.understanding-section {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  background: rgba(59, 130, 246, 0.08);
  border-left: 3px solid #3b82f6;
  border-radius: 4px;
}

.section-icon {
  font-size: 18px;
  flex-shrink: 0;
  margin-top: 2px;
}

.step-section {
  padding: 12px;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  animation: slideIn 0.3s ease-out;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.step-marker {
  font-weight: 700;
  color: #3b82f6;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.step-title-wrapper {
  font-weight: 600;
  font-size: 15px;
  color: #1f2937;
  margin-bottom: 8px;
  line-height: 1.5;
}

.step-description-wrapper {
  color: #6b7280;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 2px solid #d1d5db;
  font-style: italic;
}

.substeps-list {
  margin: 12px 0;
  padding: 8px 0;
  border-top: 1px solid #f3f4f6;
  border-bottom: 1px solid #f3f4f6;
}

.substep-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 6px 0;
  padding: 6px 8px;
  color: #4b5563;
}

.substep-icon {
  color: #9ca3af;
  font-weight: bold;
  flex-shrink: 0;
}

.step-executing {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #3b82f6;
  font-weight: 500;
  margin-top: 8px;
  font-size: 13px;
}

.executing-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: #3b82f6;
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.step-completed {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #10b981;
  font-weight: 500;
  margin-top: 8px;
  font-size: 13px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 13px;
  padding: 8px;
}

.loader {
  display: inline-block;
  width: 4px;
  height: 4px;
  background: #6b7280;
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
