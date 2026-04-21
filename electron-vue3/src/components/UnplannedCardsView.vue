<template>
  <div class="unplanned-cards-view">
    <!-- 头部 -->
    <div class="view-header">
      <div class="header-left">
        <h2>{{ t('unplannedCards.title') }}</h2>
        <span class="card-count">({{ filteredCards.length }})</span>
      </div>
      <div class="header-actions">
        <!-- 筛选器 -->
        <div class="filter-group">
          <label>{{ t('unplannedCards.filterByType') }}:</label>
          <select v-model="selectedType" class="type-filter">
            <option value="all">{{ t('unplannedCards.allTypes') }}</option>
            <option value="bug">{{ t('unplannedCards.bug') }}</option>
            <option value="badcase">{{ t('unplannedCards.badcase') }}</option>
            <option value="testcase">{{ t('unplannedCards.testcase') }}</option>
          </select>
        </div>
        
        <!-- 排序 -->
        <div class="filter-group">
          <label>{{ t('unplannedCards.sortBy') }}:</label>
          <select v-model="sortBy" class="sort-filter">
            <option value="updated">{{ t('unplannedCards.updatedAt') }}</option>
            <option value="created">{{ t('unplannedCards.createdAt') }}</option>
            <option value="priority">{{ t('unplannedCards.priority') }}</option>
            <option value="title">{{ t('unplannedCards.title') }}</option>
          </select>
        </div>
        
        <!-- 新建卡片按钮 -->
        <button class="btn-create" @click="handleCreateCard">
          <span>+</span>
          {{ t('unplannedCards.createCard') }}
        </button>
      </div>
    </div>
    
    <!-- 批量操作栏 -->
    <div class="batch-actions" v-if="selectedCards.length > 0">
      <span class="selected-count">{{ t('unplannedCards.selectedCount', { count: selectedCards.length }) }}</span>
      <button class="btn-batch" @click="handleBatchMove">
        {{ t('unplannedCards.batchMove') }}
      </button>
      <button class="btn-batch btn-batch-danger" @click="handleBatchDelete">
        {{ t('unplannedCards.batchDelete') }}
      </button>
      <button class="btn-batch" @click="clearSelection">
        {{ t('unplannedCards.clearSelection') }}
      </button>
    </div>
    
    <!-- 卡片列表 -->
    <div class="cards-grid" v-if="filteredCards.length > 0">
      <div 
        v-for="card in filteredCards" 
        :key="card.id"
        class="card-item"
        :class="{ selected: selectedCards.includes(card.id) }"
        @click="handleCardClick(card)"
      >
        <!-- 卡片头部 -->
        <div class="card-header">
          <div class="card-type-badge" :class="card.type">
            <span class="type-icon">{{ getTypeIcon(card.type) }}</span>
            <span class="type-label">{{ t(`globalSearch.${card.type}`) }}</span>
          </div>
          <div class="card-checkbox" @click.stop="toggleCardSelection(card.id)">
            <input type="checkbox" :checked="selectedCards.includes(card.id)">
          </div>
        </div>
        
        <!-- 卡片标题 -->
        <h3 class="card-title" :title="card.title">{{ card.title }}</h3>
        
        <!-- 卡片描述预览 -->
        <p class="card-description" v-if="card.description">
          {{ truncateText(card.description, 100) }}
        </p>
        
        <!-- 卡片信息 -->
        <div class="card-meta">
          <div class="meta-item" v-if="card.priority">
            <span class="meta-label">{{ t('unplannedCards.priority') }}:</span>
            <span class="priority-badge" :class="card.priority">{{ card.priority }}</span>
          </div>
          <div class="meta-item" v-if="card.assignee">
            <span class="meta-label">{{ t('unplannedCards.assignee') }}:</span>
            <span class="assignee-name">{{ card.assignee }}</span>
          </div>
        </div>
        
        <!-- 卡片底部 -->
        <div class="card-footer">
          <span class="update-time">
            {{ formatDate(card.updated_at) }}
          </span>
          <div class="card-actions">
            <button class="action-btn" @click.stop="handleEditCard(card)" :title="t('unplannedCards.edit')">
              ✏️
            </button>
            <button class="action-btn" @click.stop="handleMoveCard(card)" :title="t('unplannedCards.move')">
              📋
            </button>
            <button class="action-btn action-btn-danger" @click.stop="handleDeleteCard(card)" :title="t('unplannedCards.delete')">
              🗑️
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 空状态 -->
    <div class="empty-state" v-else>
      <div class="empty-icon">📋</div>
      <h3>{{ t('unplannedCards.emptyTitle') }}</h3>
      <p>{{ t('unplannedCards.emptyDesc') }}</p>
      <button class="btn-create" @click="handleCreateCard">
        {{ t('unplannedCards.createFirstCard') }}
      </button>
    </div>
    
    <!-- 移动卡片对话框 -->
    <CardMoveDialog
      v-if="showMoveDialog"
      :card="selectedMoveCard"
      @close="showMoveDialog = false"
      @moved="handleCardMoved"
    />
    
    <!-- 批量移动对话框 -->
    <CardMoveDialog
      v-if="showBatchMoveDialog"
      :card="batchMoveTarget"
      @close="showBatchMoveDialog = false"
      @moved="handleBatchMoved"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { getCards, deleteCard as apiDeleteCard } from '../api.js'
import CardMoveDialog from './CardMoveDialog.vue'

const { t } = useI18n()

const props = defineProps({
  projectId: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['create-card', 'edit-card', 'view-card'])

// 卡片数据
const cards = ref([])
const loading = ref(false)

// 筛选和排序
const selectedType = ref('all')
const sortBy = ref('updated')
const selectedCards = ref([])

// 移动对话框
const showMoveDialog = ref(false)
const showBatchMoveDialog = ref(false)
const selectedMoveCard = ref(null)

// 批量移动目标
const batchMoveTarget = computed(() => ({
  id: null,
  title: t('unplannedCards.batchMoveTitle'),
  type: 'batch',
  project_id: props.projectId,
  plan_id: null
}))

// 类型图标
const getTypeIcon = (type) => {
  const icons = {
    bug: '🐛',
    badcase: '⚠️',
    testcase: '✅'
  }
  return icons[type] || '📋'
}

// 文本截断
const truncateText = (text, maxLength) => {
  if (!text || text.length <= maxLength) return text
  return text.substring(0, maxLength) + '...'
}

// 日期格式化
const formatDate = (dateStr) => {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  
  if (days === 0) return t('unplannedCards.today')
  if (days === 1) return t('unplannedCards.yesterday')
  if (days < 7) return t('unplannedCards.daysAgo', { days })
  
  return date.toLocaleDateString()
}

// 筛选后的卡片
const filteredCards = computed(() => {
  let result = [...cards.value]
  
  // 按类型筛选
  if (selectedType.value !== 'all') {
    result = result.filter(card => card.type === selectedType.value)
  }
  
  // 排序
  result.sort((a, b) => {
    switch (sortBy.value) {
      case 'updated':
        return new Date(b.updated_at || 0) - new Date(a.updated_at || 0)
      case 'created':
        return new Date(b.created_at || 0) - new Date(a.created_at || 0)
      case 'priority':
        const priorityOrder = { p1: 0, p2: 1, p3: 2, p4: 3 }
        return (priorityOrder[a.priority] || 99) - (priorityOrder[b.priority] || 99)
      case 'title':
        return (a.title || '').localeCompare(b.title || '')
      default:
        return 0
    }
  })
  
  return result
})

// 加载数据
const loadCards = async () => {
  loading.value = true
  try {
    const response = await getCards({
      project_id: props.projectId,
      plan_id: null, // 只获取未计划的卡片
      per_page: 1000
    })
    if (response.data.success) {
      cards.value = response.data.data.cards || response.data.data.results || []
    }
  } catch (error) {
    console.error('加载卡片失败:', error)
  } finally {
    loading.value = false
  }
}

// 卡片选择
const toggleCardSelection = (cardId) => {
  const index = selectedCards.value.indexOf(cardId)
  if (index === -1) {
    selectedCards.value.push(cardId)
  } else {
    selectedCards.value.splice(index, 1)
  }
}

const clearSelection = () => {
  selectedCards.value = []
}

// 卡片操作
const handleCardClick = (card) => {
  emit('view-card', card)
}

const handleEditCard = (card) => {
  emit('edit-card', card)
}

const handleCreateCard = () => {
  emit('create-card')
}

const handleMoveCard = (card) => {
  selectedMoveCard.value = card
  showMoveDialog.value = true
}

const handleDeleteCard = async (card) => {
  if (!confirm(t('unplannedCards.confirmDelete', { title: card.title }))) {
    return
  }
  
  try {
    await apiDeleteCard(card.id)
    cards.value = cards.value.filter(c => c.id !== card.id)
  } catch (error) {
    console.error('删除卡片失败:', error)
    alert(t('unplannedCards.deleteFailed'))
  }
}

// 移动完成回调
const handleCardMoved = () => {
  showMoveDialog.value = false
  selectedMoveCard.value = null
  loadCards()
}

// 批量移动
const handleBatchMove = () => {
  showBatchMoveDialog.value = true
}

const handleBatchMoved = () => {
  showBatchMoveDialog.value = false
  clearSelection()
  loadCards()
}

const handleBatchDelete = async () => {
  if (!confirm(t('unplannedCards.confirmBatchDelete', { count: selectedCards.value.length }))) {
    return
  }
  
  try {
    for (const cardId of selectedCards.value) {
      await apiDeleteCard(cardId)
    }
    cards.value = cards.value.filter(c => !selectedCards.value.includes(c.id))
    clearSelection()
  } catch (error) {
    console.error('批量删除失败:', error)
    alert(t('unplannedCards.deleteFailed'))
  }
}

onMounted(() => {
  loadCards()
})
</script>

<style scoped>
.unplanned-cards-view {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e0e0e0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-left h2 {
  margin: 0;
  font-size: 20px;
  color: #333;
}

.card-count {
  color: #666;
  font-size: 14px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  font-size: 13px;
  color: #666;
}

.type-filter,
.sort-filter {
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  cursor: pointer;
}

.btn-create {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-create:hover {
  background: #1565c0;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #e3f2fd;
  border-radius: 6px;
  margin-bottom: 16px;
}

.selected-count {
  font-size: 14px;
  color: #1976d2;
  font-weight: 500;
}

.btn-batch {
  padding: 6px 12px;
  background: white;
  border: 1px solid #1976d2;
  color: #1976d2;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-batch:hover {
  background: #1976d2;
  color: white;
}

.btn-batch-danger {
  border-color: #ef5350;
  color: #ef5350;
}

.btn-batch-danger:hover {
  background: #ef5350;
  color: white;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.card-item {
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.card-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.card-item.selected {
  border-color: #1976d2;
  background: #f5f5f5;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-type-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
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

.card-checkbox input {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.card-title {
  margin: 0 0 8px 0;
  font-size: 15px;
  color: #333;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-description {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.meta-label {
  color: #999;
}

.priority-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
}

.priority-badge.p1,
.priority-badge.P0 {
  background: #ffcdd2;
  color: #c62828;
}

.priority-badge.p2,
.priority-badge.P1 {
  background: #ffe0b2;
  color: #ef6c00;
}

.priority-badge.p3,
.priority-badge.P2,
.priority-badge.P3 {
  background: #e0e0e0;
  color: #616161;
}

.assignee-name {
  color: #333;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.update-time {
  font-size: 12px;
  color: #999;
}

.card-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 4px 8px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.action-btn:hover {
  opacity: 1;
}

.action-btn-danger:hover {
  opacity: 1;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: #333;
}

.empty-state p {
  margin: 0 0 24px 0;
  font-size: 14px;
  color: #666;
}
</style>
