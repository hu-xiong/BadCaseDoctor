<template>
  <div class="card-list">
    <div class="card-list-header">
      <div class="card-list-title">
        {{ title }}
        <span v-if="cards.length > 0" class="card-count">({{ cards.length }})</span>
      </div>
      <button v-if="showCreateButton" class="btn btn-primary" @click="handleCreateCard">
        {{ t('cardList.createCard') }}
      </button>
    </div>
    
    <div v-if="cards.length === 0" class="card-list-empty">
      <div class="empty-icon">📋</div>
      <div class="empty-text">{{ t('cardList.emptyText') }}</div>
      <button v-if="showCreateButton" class="btn btn-primary" @click="handleCreateCard">
        {{ t('cardList.createFirstCard') }}
      </button>
    </div>
    
    <div v-else class="card-list-body">
      <div class="card-list-table">
        <div class="table-header">
          <div class="table-cell table-cell-id">ID</div>
          <div class="table-cell table-cell-title">{{ t('cardList.title') }}</div>
          <div class="table-cell table-cell-type">{{ t('cardList.type') }}</div>
          <div class="table-cell table-cell-status">{{ t('cardList.status') }}</div>
          <div class="table-cell table-cell-assignee">{{ t('cardList.assignee') }}</div>
          <div class="table-cell table-cell-created">{{ t('cardList.createdAt') }}</div>
          <div class="table-cell table-cell-actions">{{ t('cardList.actions') }}</div>
        </div>
        <div v-for="card in cards" :key="card.id" class="table-row">
          <div class="table-cell table-cell-id">{{ card.id }}</div>
          <div class="table-cell table-cell-title">
            <span class="card-title" @click="handleViewCard(card)">{{ card.title }}</span>
          </div>
          <div class="table-cell table-cell-type">
            <span class="card-type-tag" :class="`type-${card.type}`">
              {{ getCardTypeLabel(card.type) }}
            </span>
          </div>
          <div class="table-cell table-cell-status">
            <span class="card-status-tag" :class="`status-${card.status}`">
              {{ card.status }}
            </span>
          </div>
          <div class="table-cell table-cell-assignee">{{ card.assignee || '-' }}</div>
          <div class="table-cell table-cell-created">{{ formatDate(card.createdAt) }}</div>
          <div class="table-cell table-cell-actions">
            <button class="action-btn view-btn" @click="handleViewCard(card)">
              {{ t('cardList.view') }}
            </button>
            <button class="action-btn edit-btn" @click="handleEditCard(card)">
              {{ t('cardList.edit') }}
            </button>
            <button class="action-btn delete-btn" @click="handleDeleteCard(card)">
              {{ t('cardList.delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getProjectCards, deleteCardWithCascadeConfirm, cascadeCardDeleteConfirmText } from '../api.js'

const { t } = useI18n()

const cascadeCardDeleteConfirm = (payload) =>
  confirm(cascadeCardDeleteConfirmText(t, { ...payload, source_kind: payload.source_kind || 'badcase' }))

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  projectId: {
    type: [String, Number],
    required: true
  },
  showCreateButton: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['create', 'view', 'edit', 'delete'])

const cards = ref([])
const loading = ref(false)
const error = ref(null)

onMounted(() => {
  loadCards()
})

const loadCards = async () => {
  loading.value = true
  error.value = null
  try {
    const response = await getProjectCards(props.projectId)
    if (response.data.success) {
      cards.value = response.data.data
    } else {
      error.value = response.data.error || '获取卡片列表失败'
    }
  } catch (err) {
    console.error('获取卡片列表失败:', err)
    error.value = '获取卡片列表失败'
  } finally {
    loading.value = false
  }
}

const handleCreateCard = () => {
  emit('create')
}

const handleViewCard = (card) => {
  emit('view', card)
}

const handleEditCard = (card) => {
  emit('edit', card)
}

const handleDeleteCard = async (card) => {
  if (confirm(t('cardList.deleteConfirm'))) {
    try {
      const response = await deleteCardWithCascadeConfirm(card.id, { confirmFn: cascadeCardDeleteConfirm })
      if (response?.data?.cancelled) return
      if (response.data.success) {
        cards.value = cards.value.filter(c => c.id !== card.id)
        emit('delete', card)
      } else {
        alert(response.data.error || '删除卡片失败')
      }
    } catch (err) {
      console.error('删除卡片失败:', err)
      alert('删除卡片失败')
    }
  }
}

const getCardTypeLabel = (type) => {
  const typeLabels = {
    bug: t('cardList.bug'),
    badcase: t('cardList.badcase'),
    testcase: t('cardList.testcase')
  }
  return typeLabels[type] || type
}

const formatDate = (date) => {
  if (!date) return ''
  const d = new Date(date)
  return d.toLocaleString()
}

defineExpose({
  loadCards
})
</script>

<style scoped>
.card-list {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 16px;
}

.card-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e8e8e8;
}

.card-list-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.card-count {
  font-size: 14px;
  font-weight: normal;
  color: #999;
  margin-left: 8px;
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

.card-list-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 14px;
  color: #999;
  margin-bottom: 24px;
}

.card-list-body {
  overflow-x: auto;
}

.card-list-table {
  width: 100%;
  border-collapse: collapse;
}

.table-header {
  display: flex;
  background-color: #fafafa;
  border-bottom: 1px solid #e8e8e8;
  font-weight: 600;
  font-size: 14px;
  color: #333;
}

.table-row {
  display: flex;
  border-bottom: 1px solid #e8e8e8;
  transition: background-color 0.3s;
}

.table-row:hover {
  background-color: #f5f5f5;
}

.table-cell {
  padding: 12px;
  flex: 1;
  font-size: 14px;
  color: #333;
}

.table-cell-id {
  flex: 0 0 80px;
  color: #999;
}

.table-cell-title {
  flex: 0 0 300px;
}

.table-cell-type {
  flex: 0 0 120px;
}

.table-cell-status {
  flex: 0 0 120px;
}

.table-cell-assignee {
  flex: 0 0 150px;
}

.table-cell-created {
  flex: 0 0 200px;
  color: #999;
}

.table-cell-actions {
  flex: 0 0 180px;
  display: flex;
  gap: 8px;
}

.card-title {
  cursor: pointer;
  color: #1890ff;
  text-decoration: none;
}

.card-title:hover {
  text-decoration: underline;
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

.action-btn {
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.3s;
  background-color: #fff;
}

.view-btn {
  color: #1890ff;
  border-color: #1890ff;
}

.view-btn:hover {
  background-color: #e6f7ff;
}

.edit-btn {
  color: #faad14;
  border-color: #faad14;
}

.edit-btn:hover {
  background-color: #fffbe6;
}

.delete-btn {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

.delete-btn:hover {
  background-color: #fff1f0;
}
</style>