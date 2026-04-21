<template>
  <div class="card-detail">
    <div class="card-detail-header">
      <div class="card-detail-title">
        <span class="card-type-icon" :class="`type-${card.type}`"></span>
        <h2>{{ card.title }}</h2>
        <span class="card-id">#{{ card.id }}</span>
      </div>
      <div class="card-detail-actions">
        <button class="btn btn-move" @click="handleMove">
          📋 {{ t('cardDetail.move') }}
        </button>
        <button class="btn btn-primary" @click="handleEdit">
          {{ t('cardDetail.edit') }}
        </button>
        <button class="btn btn-cancel" @click="handleClose">
          {{ t('cardDetail.close') }}
        </button>
      </div>
    </div>
    
    <div class="card-detail-body">
      <div class="card-detail-section">
        <h3 class="section-title">{{ t('cardDetail.basicInfo') }}</h3>
        <div class="info-grid">
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.type') }}:</label>
            <span class="info-value">
              <span class="card-type-tag" :class="`type-${card.type}`">
                {{ getCardTypeLabel(card.type) }}
              </span>
            </span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.status') }}:</label>
            <span class="info-value">
              <span class="card-status-tag" :class="`status-${card.status}`">
                {{ card.status }}
              </span>
            </span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.assignee') }}:</label>
            <span class="info-value">{{ card.assignee || '-' }}</span>
          </div>
          <div class="info-item" v-if="card.plan_id">
            <label class="info-label">{{ t('cardDetail.plan') }}:</label>
            <span class="info-value">{{ card.plan_name || '#' + card.plan_id }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.createdAt') }}:</label>
            <span class="info-value">{{ formatDate(card.createdAt) }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.updatedAt') }}:</label>
            <span class="info-value">{{ formatDate(card.updatedAt) }}</span>
          </div>
        </div>
      </div>
      
      <div class="card-detail-section">
        <h3 class="section-title">{{ t('cardDetail.description') }}</h3>
        <div class="card-description">
          {{ card.description || t('cardDetail.noDescription') }}
        </div>
      </div>
      
      <div class="card-detail-section" v-if="card.type === 'bug'">
        <h3 class="section-title">{{ t('cardDetail.bugInfo') }}</h3>
        <div class="info-grid">
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.severity') }}:</label>
            <span class="info-value">{{ card.severity || '-' }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.priority') }}:</label>
            <span class="info-value">{{ card.priority || '-' }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.reproducer') }}:</label>
            <span class="info-value">{{ card.reproducer || '-' }}</span>
          </div>
        </div>
      </div>
      
      <div class="card-detail-section" v-if="card.type === 'badcase'">
        <h3 class="section-title">{{ t('cardDetail.badcaseInfo') }}</h3>
        <div class="info-grid">
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.scenario') }}:</label>
            <span class="info-value">{{ card.scenario || '-' }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.expected') }}:</label>
            <span class="info-value">{{ card.expected || '-' }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.actual') }}:</label>
            <span class="info-value">{{ card.actual || '-' }}</span>
          </div>
        </div>
      </div>
      
      <div class="card-detail-section" v-if="card.type === 'testcase'">
        <h3 class="section-title">{{ t('cardDetail.testcaseInfo') }}</h3>
        <div class="info-grid">
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.steps') }}:</label>
            <span class="info-value">{{ card.steps || '-' }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.expectedResult') }}:</label>
            <span class="info-value">{{ card.expectedResult || '-' }}</span>
          </div>
          <div class="info-item">
            <label class="info-label">{{ t('cardDetail.testResult') }}:</label>
            <span class="info-value">{{ card.testResult || '-' }}</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 移动卡片对话框 -->
    <CardMoveDialog
      v-if="showMoveDialog"
      :card="card"
      @close="showMoveDialog = false"
      @moved="handleMoved"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import CardMoveDialog from './CardMoveDialog.vue'

const { t } = useI18n()

const props = defineProps({
  card: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['edit', 'close', 'moved'])

const showMoveDialog = ref(false)

const handleEdit = () => {
  emit('edit', props.card)
}

const handleClose = () => {
  emit('close')
}

const handleMove = () => {
  showMoveDialog.value = true
}

const handleMoved = (result) => {
  showMoveDialog.value = false
  emit('moved', result)
}

const getCardTypeLabel = (type) => {
  const typeLabels = {
    bug: t('cardDetail.bug'),
    badcase: t('cardDetail.badcase'),
    testcase: t('cardDetail.testcase')
  }
  return typeLabels[type] || type
}

const formatDate = (date) => {
  if (!date) return ''
  const d = new Date(date)
  return d.toLocaleString()
}
</script>

<style scoped>
.card-detail {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 24px;
  min-height: 400px;
}

.card-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e8e8e8;
}

.card-detail-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.card-type-icon {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.type-bug {
  background-color: #ff4d4f;
  color: #fff;
}

.type-badcase {
  background-color: #faad14;
  color: #fff;
}

.type-testcase {
  background-color: #1890ff;
  color: #fff;
}

.card-detail-title h2 {
  font-size: 20px;
  font-weight: 600;
  color: #333;
  margin: 0;
  flex: 1;
}

.card-id {
  font-size: 14px;
  color: #999;
  font-weight: normal;
}

.card-detail-actions {
  display: flex;
  gap: 8px;
}

.btn {
  padding: 8px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-primary {
  background-color: #1890ff;
  border-color: #1890ff;
  color: #fff;
}

.btn-primary:hover {
  background-color: #40a9ff;
  border-color: #40a9ff;
}

.btn-cancel {
  background-color: #fff;
  color: #333;
}

.btn-cancel:hover {
  border-color: #1890ff;
  color: #1890ff;
}

.card-detail-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.card-detail-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #e8e8e8;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 14px;
  font-weight: 500;
  color: #666;
}

.info-value {
  font-size: 14px;
  color: #333;
  line-height: 1.4;
}

.card-type-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}

.type-bug {
  background-color: #fff1f0;
  color: #ff4d4f;
  border: 1px solid #ffccc7;
}

.type-badcase {
  background-color: #fffbe6;
  color: #faad14;
  border: 1px solid #ffe58f;
}

.type-testcase {
  background-color: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.card-status-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}

.status-open {
  background-color: #f6ffed;
  color: #52c41a;
  border: 1px solid #b7eb8f;
}

.status-in-progress {
  background-color: #e6f7ff;
  color: #1890ff;
  border: 1px solid #91d5ff;
}

.status-closed {
  background-color: #f5f5f5;
  color: #999;
  border: 1px solid #d9d9d9;
}

.card-description {
  font-size: 14px;
  color: #333;
  line-height: 1.5;
  white-space: pre-wrap;
}
</style>