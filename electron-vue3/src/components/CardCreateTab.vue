<template>
  <div class="card-create-tab">
    <div class="create-tab-header">
      <h2 class="tab-title">{{ t('cardCreateTab.title') }}</h2>
      <button class="close-btn" @click="handleClose">×</button>
    </div>

    <!-- 步骤1：选择卡片类型 -->
    <div v-if="currentStep === 'select-type'" class="step-container">
      <div class="step-header">
        <span class="step-number">1</span>
        <span class="step-title">{{ t('cardCreateTab.selectType') }}</span>
      </div>
      <div class="type-selector">
        <div
          v-for="type in cardTypes"
          :key="type.value"
          class="type-card"
          @click="selectType(type)"
        >
          <div class="type-icon" :class="`type-${type.value}`">
            {{ type.icon }}
          </div>
          <div class="type-info">
            <div class="type-name">{{ type.label }}</div>
            <div class="type-desc">{{ type.description }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 步骤2：填写基本信息 -->
    <div v-if="currentStep === 'basic-info'" class="step-container">
      <div class="step-header">
        <span class="step-number">2</span>
        <span class="step-title">{{ t('cardCreateTab.basicInfo') }}</span>
        <button class="back-btn" @click="goBackToTypeSelect">← {{ t('cardCreateTab.back') }}</button>
      </div>

      <div class="form-section">
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.cardType') }}</label>
          <div class="selected-type">
            <span class="type-icon-small" :class="`type-${selectedCardType.value}`">
              {{ selectedCardType.icon }}
            </span>
            <span>{{ selectedCardType.label }}</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label required">{{ t('cardCreateTab.title') }}</label>
          <input
            v-model="cardData.title"
            type="text"
            class="form-input"
            :placeholder="t('cardCreateTab.titlePlaceholder')"
            @keyup.enter="goToDetailInfo"
          />
        </div>

        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.description') }}</label>
          <textarea
            v-model="cardData.description"
            class="form-textarea"
            :placeholder="t('cardCreateTab.descriptionPlaceholder')"
            rows="4"
          ></textarea>
        </div>

        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.assignee') }}</label>
          <select v-model="cardData.assignee_id" class="form-select">
            <option value="">{{ t('cardCreateTab.selectAssignee') }}</option>
            <option v-for="member in projectMembers" :key="member.id" :value="member.id">
              {{ member.name }}
            </option>
          </select>
        </div>

        <div class="form-actions">
          <button class="btn btn-secondary" @click="handleClose">
            {{ t('cardCreateTab.cancel') }}
          </button>
          <button
            class="btn btn-primary"
            @click="goToDetailInfo"
            :disabled="!cardData.title.trim()"
          >
            {{ t('cardCreateTab.next') }} →
          </button>
        </div>
      </div>
    </div>

    <!-- 步骤3：详细信息 (根据类型不同显示不同字段) -->
    <div v-if="currentStep === 'detail-info'" class="step-container">
      <div class="step-header">
        <span class="step-number">3</span>
        <span class="step-title">{{ t('cardCreateTab.detailInfo') }}</span>
        <button class="back-btn" @click="goBackToBasicInfo">← {{ t('cardCreateTab.back') }}</button>
      </div>

      <!-- Bug特有字段 -->
      <div v-if="selectedCardType.value === 'bug'" class="form-section">
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.severity') }}</label>
          <select v-model="cardData.severity" class="form-select">
            <option value="low">{{ t('cardCreateTab.severityLow') }}</option>
            <option value="medium">{{ t('cardCreateTab.severityMedium') }}</option>
            <option value="high">{{ t('cardCreateTab.severityHigh') }}</option>
            <option value="critical">{{ t('cardCreateTab.severityCritical') }}</option>
          </select>
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.priority') }}</label>
          <select v-model="cardData.priority" class="form-select">
            <option value="low">{{ t('cardCreateTab.priorityLow') }}</option>
            <option value="medium">{{ t('cardCreateTab.priorityMedium') }}</option>
            <option value="high">{{ t('cardCreateTab.priorityHigh') }}</option>
          </select>
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.reproducer') }}</label>
          <input
            v-model="cardData.reproducer"
            type="text"
            class="form-input"
            :placeholder="t('cardCreateTab.reproducerPlaceholder')"
          />
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.steps') }}</label>
          <textarea
            v-model="cardData.steps"
            class="form-textarea"
            :placeholder="t('cardCreateTab.stepsPlaceholder')"
            rows="4"
          ></textarea>
        </div>
      </div>

      <!-- BadCase特有字段 -->
      <div v-else-if="selectedCardType.value === 'badcase'" class="form-section">
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.scenario') }}</label>
          <input
            v-model="cardData.scenario"
            type="text"
            class="form-input"
            :placeholder="t('cardCreateTab.scenarioPlaceholder')"
          />
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.expected') }}</label>
          <textarea
            v-model="cardData.expected"
            class="form-textarea"
            :placeholder="t('cardCreateTab.expectedPlaceholder')"
            rows="3"
          ></textarea>
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.actual') }}</label>
          <textarea
            v-model="cardData.actual"
            class="form-textarea"
            :placeholder="t('cardCreateTab.actualPlaceholder')"
            rows="3"
          ></textarea>
        </div>
      </div>

      <!-- TestCase特有字段 -->
      <div v-else-if="selectedCardType.value === 'testcase'" class="form-section">
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.testSteps') }}</label>
          <textarea
            v-model="cardData.steps"
            class="form-textarea"
            :placeholder="t('cardCreateTab.testStepsPlaceholder')"
            rows="4"
          ></textarea>
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.expectedResult') }}</label>
          <textarea
            v-model="cardData.expected_result"
            class="form-textarea"
            :placeholder="t('cardCreateTab.expectedResultPlaceholder')"
            rows="3"
          ></textarea>
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreateTab.precondition') }}</label>
          <textarea
            v-model="cardData.precondition"
            class="form-textarea"
            :placeholder="t('cardCreateTab.preconditionPlaceholder')"
            rows="2"
          ></textarea>
        </div>
      </div>

      <div class="form-actions">
        <button class="btn btn-secondary" @click="handleClose">
          {{ t('cardCreateTab.cancel') }}
        </button>
        <button
          class="btn btn-primary"
          @click="handleCreateCard"
          :disabled="loading"
        >
          {{ loading ? t('cardCreateTab.creating') : t('cardCreateTab.create') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { createCard } from '../api'

const { t } = useI18n()

const props = defineProps({
  projectId: {
    type: [String, Number],
    required: true
  },
  projectMembers: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['created', 'close', 'tab-title'])

const currentStep = ref('select-type')
const selectedCardType = ref(null)
const loading = ref(false)
const error = ref(null)

const cardData = reactive({
  title: '',
  description: '',
  assignee_id: '',
  severity: 'medium',
  priority: 'medium',
  reproducer: '',
  steps: '',
  scenario: '',
  expected: '',
  actual: '',
  expected_result: '',
  precondition: ''
})

const cardTypes = [
  {
    value: 'bug',
    label: t('cardCreateTab.bug'),
    icon: '🐛',
    description: t('cardCreateTab.bugDesc')
  },
  {
    value: 'badcase',
    label: t('cardCreateTab.badcase'),
    icon: '📋',
    description: t('cardCreateTab.badcaseDesc')
  },
  {
    value: 'testcase',
    label: t('cardCreateTab.testcase'),
    icon: '🧪',
    description: t('cardCreateTab.testcaseDesc')
  }
]

const selectType = (type) => {
  selectedCardType.value = type
  emit('tab-title', `${t('cardCreateTab.create')} ${type.label}`)
}

const goBackToTypeSelect = () => {
  currentStep.value = 'select-type'
  emit('tab-title', t('cardCreateTab.title'))
}

const goToDetailInfo = () => {
  if (!cardData.title.trim()) return
  currentStep.value = 'detail-info'
  emit('tab-title', `${t('cardCreateTab.create')} ${selectedCardType.value.label}`)
}

const goBackToBasicInfo = () => {
  currentStep.value = 'basic-info'
  emit('tab-title', `${t('cardCreateTab.create')} ${selectedCardType.value.label}`)
}

const handleCreateCard = async () => {
  if (!cardData.title.trim()) return

  loading.value = true
  error.value = null

  try {
    const payload = {
      title: cardData.title.trim(),
      type: selectedCardType.value.value,
      project_id: props.projectId,
      description: cardData.description,
      assignee_id: cardData.assignee_id || null,
      status: 'open'
    }

    // 添加类型特有字段
    if (selectedCardType.value.value === 'bug') {
      payload.severity = cardData.severity
      payload.priority = cardData.priority
      payload.reproducer = cardData.reproducer
      payload.steps = cardData.steps
    } else if (selectedCardType.value.value === 'badcase') {
      payload.scenario = cardData.scenario
      payload.expected = cardData.expected
      payload.actual = cardData.actual
    } else if (selectedCardType.value.value === 'testcase') {
      payload.steps = cardData.steps
      payload.expected_result = cardData.expected_result
      payload.precondition = cardData.precondition
    }

    const response = await createCard(payload)

    if (response.data.success) {
      emit('created', response.data.data)
      handleClose()
    } else {
      error.value = response.data.error || t('cardCreateTab.createFailed')
    }
  } catch (err) {
    console.error('创建卡片失败:', err)
    error.value = t('cardCreateTab.createFailed')
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  emit('close')
}
</script>

<style scoped>
.card-create-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.create-tab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
  flex-shrink: 0;
}

.tab-title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: #999;
  cursor: pointer;
  padding: 0 8px;
  line-height: 1;
}

.close-btn:hover {
  color: #666;
}

.step-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.step-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #1890ff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
}

.step-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.back-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: #1890ff;
  cursor: pointer;
  font-size: 14px;
}

.back-btn:hover {
  text-decoration: underline;
}

.type-selector {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 16px;
  border: 2px solid #e8e8e8;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.type-card:hover {
  border-color: #1890ff;
  box-shadow: 0 4px 12px rgba(24, 144, 255, 0.15);
}

.type-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  margin-bottom: 12px;
}

.type-icon.type-bug {
  background: #fff1f0;
}

.type-icon.type-badcase {
  background: #fffbe6;
}

.type-icon.type-testcase {
  background: #e6f7ff;
}

.type-info {
  text-align: center;
}

.type-name {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}

.type-desc {
  font-size: 12px;
  color: #999;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 600px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.form-label.required::after {
  content: ' *';
  color: #ff4d4f;
}

.selected-type {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 4px;
  font-size: 14px;
}

.type-icon-small {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.type-icon-small.type-bug {
  background: #fff1f0;
}

.type-icon-small.type-badcase {
  background: #fffbe6;
}

.type-icon-small.type-testcase {
  background: #e6f7ff;
}

.form-input,
.form-select,
.form-textarea {
  padding: 10px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s;
}

.form-input:focus,
.form-select:focus,
.form-textarea:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e8e8e8;
}

.btn {
  padding: 10px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #1890ff;
  border: 1px solid #1890ff;
  color: #fff;
}

.btn-primary:hover {
  background: #40a9ff;
  border-color: #40a9ff;
}

.btn-primary:disabled {
  background: #d9d9d9;
  border-color: #d9d9d9;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  border: 1px solid #d9d9d9;
  color: #333;
}

.btn-secondary:hover {
  border-color: #1890ff;
  color: #1890ff;
}
</style>
