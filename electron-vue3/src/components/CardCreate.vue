<template>
  <div class="card-create">
    <div class="card-create-header">
      <span class="card-create-title">{{ t('cardCreate.title') }}</span>
      <button class="card-create-close" @click="close">×</button>
    </div>
    <div class="card-create-body">
      <div class="card-form">
        <div v-if="error" class="error-message">{{ error }}</div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreate.titleLabel') }}</label>
          <input
            v-model="cardTitle"
            type="text"
            class="form-input"
            :placeholder="t('cardCreate.titlePlaceholder')"
            @keyup.enter="createCard"
            :disabled="loading"
          />
        </div>
        <div class="form-item">
          <label class="form-label">{{ t('cardCreate.typeLabel') }}</label>
          <div class="form-value">{{ cardType?.label || '' }}</div>
        </div>
        <div class="form-actions">
          <button class="btn btn-cancel" @click="close" :disabled="loading">
            {{ t('cardCreate.cancel') }}
          </button>
          <button class="btn btn-primary" @click="createCard" :disabled="!cardTitle.trim() || loading">
            {{ loading ? t('cardCreate.creating') : t('cardCreate.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { createCard as createCardApi } from '../api'

const { t } = useI18n()

const props = defineProps({
  cardType: {
    type: Object,
    required: true
  },
  projectId: {
    type: [String, Number],
    required: true
  }
})

const emit = defineEmits(['create', 'close'])

const cardTitle = ref('')
const loading = ref(false)
const error = ref(null)

const createCard = async () => {
  if (!cardTitle.value.trim()) return
  
  loading.value = true
  error.value = null
  
  try {
    const response = await createCardApi({
      title: cardTitle.value.trim(),
      type: props.cardType.value,
      project_id: props.projectId
    })
    
    if (response.data.success) {
      emit('create', response.data.data)
      close()
    } else {
      error.value = response.data.error || '创建卡片失败'
    }
  } catch (err) {
    console.error('创建卡片失败:', err)
    error.value = '创建卡片失败'
  } finally {
    loading.value = false
  }
}

const close = () => {
  cardTitle.value = ''
  error.value = null
  emit('close')
}
</script>

<style scoped>
.card-create {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  width: 400px;
}

.card-create-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #e8e8e8;
}

.card-create-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.card-create-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.3s;
}

.card-create-close:hover {
  background-color: #f5f5f5;
  color: #333;
}

.card-create-body {
  padding: 16px;
}

.card-type-selection {
  margin-bottom: 16px;
}

.card-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.error-message {
  padding: 8px 12px;
  background-color: #fff1f0;
  border: 1px solid #ffccc7;
  border-radius: 4px;
  color: #ff4d4f;
  font-size: 14px;
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

.form-input {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  transition: all 0.3s;
}

.form-input:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

.form-value {
  padding: 8px 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  background-color: #f5f5f5;
  color: #333;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.btn {
  padding: 8px 16px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-cancel {
  background-color: #fff;
  color: #333;
}

.btn-cancel:hover {
  border-color: #1890ff;
  color: #1890ff;
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

.btn-primary:disabled {
  background-color: #f5f5f5;
  border-color: #d9d9d9;
  color: #bfbfbf;
  cursor: not-allowed;
}
</style>