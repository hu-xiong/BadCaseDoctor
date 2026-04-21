<template>
  <div class="card-move-dialog-overlay" @click.self="handleClose">
    <div class="card-move-dialog">
      <div class="dialog-header">
        <h3>{{ t('cardMove.title') }}</h3>
        <button class="close-btn" @click="handleClose">×</button>
      </div>
      
      <div class="dialog-body">
        <div class="card-info">
          <div class="card-title">{{ card.title }}</div>
          <div class="card-type-badge" :class="card.type">
            {{ t(`globalSearch.${card.type}`) }}
          </div>
        </div>
        
        <div class="current-plan" v-if="card.plan_id">
          <span class="label">{{ t('cardMove.currentPlan') }}:</span>
          <span class="value">{{ currentPlanName }}</span>
        </div>
        
        <div class="move-options">
          <h4>{{ t('cardMove.selectTargetPlan') }}</h4>
          
          <!-- 未计划选项 -->
          <div 
            class="plan-option" 
            :class="{ selected: targetPlanId === null, 'no-plan': true }"
            @click="targetPlanId = null"
          >
            <span class="plan-icon">📋</span>
            <span class="plan-name">{{ t('cardMove.unplanned') }}</span>
          </div>
          
          <!-- 迭代计划列表 -->
          <div 
            v-for="plan in plans" 
            :key="plan.id"
            class="plan-option"
            :class="{ selected: targetPlanId === plan.id }"
            @click="targetPlanId = plan.id"
          >
            <span class="plan-icon">{{ getPlanIcon(plan) }}</span>
            <span class="plan-name">{{ plan.name }}</span>
            <span class="plan-status" v-if="plan.status">({{ getStatusText(plan.status) }})</span>
          </div>
        </div>
        
        <div class="history-section" v-if="planHistory.length > 0">
          <h4>{{ t('cardMove.moveHistory') }}</h4>
          <div class="history-list">
            <div 
              v-for="(item, index) in planHistory" 
              :key="index"
              class="history-item"
              :class="{ current: item.is_current }"
            >
              <span class="history-icon">{{ item.is_current ? '📍' : '✓' }}</span>
              <span class="history-plan">{{ item.plan_name }}</span>
              <span class="history-time">{{ formatTime(item.added_at) }}</span>
            </div>
          </div>
        </div>
      </div>
      
      <div class="dialog-footer">
        <button class="btn btn-cancel" @click="handleClose">
          {{ t('cardMove.cancel') }}
        </button>
        <button 
          class="btn btn-primary" 
          @click="handleMove" 
          :disabled="moving || targetPlanId === card.plan_id"
        >
          {{ moving ? t('cardMove.moving') : t('cardMove.confirm') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { moveCard, getCardPlanHistory, getProjectPlans } from '../api.js'

const { t } = useI18n()

const props = defineProps({
  card: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['close', 'moved'])

const targetPlanId = ref(props.card.plan_id)
const moving = ref(false)
const planHistory = ref([])
const plans = ref([])

const currentPlanName = computed(() => {
  if (!props.card.plan_id) return t('cardMove.unplanned')
  const plan = plans.value.find(p => p.id === props.card.plan_id)
  return plan ? plan.name : ''
})

const getPlanIcon = (plan) => {
  if (plan.status === 'completed') return '✅'
  if (plan.status === 'active') return '🔄'
  if (plan.status === 'planning') return '📝'
  return '📋'
}

const getStatusText = (status) => {
  const statusMap = {
    'planning': t('cardMove.statusPlanning'),
    'active': t('cardMove.statusActive'),
    'completed': t('cardMove.statusCompleted')
  }
  return statusMap[status] || status
}

const formatTime = (timeStr) => {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  return date.toLocaleDateString()
}

const handleClose = () => {
  emit('close')
}

const handleMove = async () => {
  if (moving.value || targetPlanId.value === props.card.plan_id) return
  
  moving.value = true
  try {
    await moveCard(props.card.id, targetPlanId.value)
    emit('moved', { cardId: props.card.id, planId: targetPlanId.value })
    emit('close')
  } catch (error) {
    console.error('移动卡片失败:', error)
    alert(t('cardMove.moveFailed'))
  } finally {
    moving.value = false
  }
}

onMounted(async () => {
  // 获取计划列表
  if (props.card.project_id) {
    try {
      const response = await getProjectPlans(props.card.project_id)
      if (response.data.success) {
        plans.value = response.data.data || []
      }
    } catch (error) {
      console.error('获取计划列表失败:', error)
    }
  }
  
  // 获取卡片历史
  try {
    const response = await getCardPlanHistory(props.card.id)
    if (response.data.success) {
      planHistory.value = response.data.data || []
    }
  } catch (error) {
    console.error('获取卡片历史失败:', error)
  }
})
</script>

<style scoped>
.card-move-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.card-move-dialog {
  background: white;
  border-radius: 8px;
  width: 480px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}

.dialog-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #666;
}

.dialog-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.card-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 6px;
}

.card-title {
  font-weight: 600;
  color: #333;
  flex: 1;
}

.card-type-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.card-type-badge.bug {
  background: #ffebee;
  color: #c62828;
}

.card-type-badge.badcase {
  background: #fff3e0;
  color: #ef6c00;
}

.card-type-badge.testcase {
  background: #e3f2fd;
  color: #1565c0;
}

.current-plan {
  margin-bottom: 20px;
  color: #666;
  font-size: 14px;
}

.current-plan .label {
  margin-right: 8px;
}

.current-plan .value {
  font-weight: 500;
  color: #333;
}

.move-options h4,
.history-section h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #666;
}

.move-options {
  margin-bottom: 20px;
}

.plan-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.plan-option:hover {
  border-color: #1976d2;
  background: #f5f5f5;
}

.plan-option.selected {
  border-color: #1976d2;
  background: #e3f2fd;
}

.plan-icon {
  font-size: 16px;
}

.plan-name {
  flex: 1;
  font-size: 14px;
  color: #333;
}

.plan-status {
  font-size: 12px;
  color: #999;
}

.no-plan {
  background: #fafafa;
}

.no-plan.selected {
  background: #e8f5e9;
  border-color: #4caf50;
}

.history-section {
  border-top: 1px solid #eee;
  padding-top: 16px;
  margin-top: 16px;
}

.history-list {
  max-height: 150px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  font-size: 13px;
  color: #666;
}

.history-item.current {
  color: #1976d2;
  font-weight: 500;
}

.history-icon {
  font-size: 12px;
}

.history-plan {
  flex: 1;
}

.history-time {
  font-size: 12px;
  color: #999;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid #eee;
}

.btn {
  padding: 8px 20px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.btn-cancel {
  background: #f5f5f5;
  color: #666;
}

.btn-cancel:hover {
  background: #e0e0e0;
}

.btn-primary {
  background: #1976d2;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1565c0;
}

.btn-primary:disabled {
  background: #b0bec5;
  cursor: not-allowed;
}
</style>
