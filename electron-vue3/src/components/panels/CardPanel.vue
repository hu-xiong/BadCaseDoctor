<template>
  <div class="card-list-panel">
    <!-- 头部信息 -->
    <div v-if="showHeader" class="content-header">
      <div class="content-title">
        <button v-if="currentTypeFilter" class="back-btn" @click="clearTypeFilter">
          ← {{ t('common.back') }}
        </button>
        <span v-if="currentTypeFilter" class="type-filter-label">
          {{ getTypeText(currentTypeFilter) }}
        </span>
        <span v-else>{{ title }}</span>
        <span class="completion-rate">{{ filteredItems.length }}/{{ total }}</span>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="content-toolbar">
      <div class="toolbar-left">
        <button class="quick-create-btn" @click="startCreate">
          {{ t('list.quickCreate', { type: itemTypeLabel }) }}
        </button>
      </div>

      <div class="toolbar-right">
        <div class="search-input-container">
          <input
            type="text"
            :value="searchText"
            :placeholder="t('list.searchPlaceholder')"
            class="search-input"
            @input="(e) => emit('update:searchText', e.target.value)"
            @keyup.enter="emit('search')"
          />
          <span class="search-icon">🔍</span>
        </div>

        <button class="refresh-btn" :disabled="loading" @click="emit('refresh')">🔄</button>
        <button
          v-if="selectedItems && selectedItems.length > 0"
          class="batch-delete-btn"
          @click.stop="batchDeleteSelected"
          :title="t('list.batchDeleteTitle', { n: selectedItems.length })"
        >
          {{ t('list.batchDelete', { n: selectedItems.length }) }}
        </button>
      </div>
    </div>

    <!-- 卡片列表表格 -->
    <div class="card-table">
      <div class="table-header">
        <div class="header-checkbox">
          <input type="checkbox" :checked="selectAll" @change="emit('toggleSelectAll')" />
        </div>
        <div class="header-title">{{ t('list.colTitle', { type: itemTypeLabel }) }}</div>
        <div class="header-status">{{ t('list.colType') }}</div>
        <div class="header-date">{{ t('list.colCreated') }}</div>
        <div class="header-actions">{{ t('list.colActions') }}</div>
      </div>

      <div class="table-body">
        <!-- 新建行（输入框 + 类型选择） -->
        <div v-if="isCreating" class="table-row creating-row">
          <div class="row-checkbox">
            <span class="new-indicator">🆕</span>
          </div>
          <div class="row-title">
            <input
              ref="createInputRef"
              v-model="newCardTitle"
              type="text"
              class="create-input"
              :placeholder="t('cardCreate.titlePlaceholder')"
              @keyup.enter="confirmCreate"
              @keyup.esc="cancelCreate"
              @blur="handleCreateBlur"
            />
          </div>
          <div class="row-status">
            <select v-model="newCardType" class="type-select">
              <option value="bug">{{ t('list.types.bug') }}</option>
              <option value="badcase">{{ t('list.types.badcase') }}</option>
              <option value="testcase">{{ t('list.types.testCase') }}</option>
            </select>
          </div>
          <div class="row-date">
            <span class="date-text creating">—</span>
          </div>
          <div class="row-actions">
            <button class="btn-icon-confirm" @mousedown.prevent="confirmCreate" :disabled="!newCardTitle.trim()" :title="t('common.confirm')">✓</button>
            <button class="btn-icon-cancel" @mousedown.prevent="cancelCreate" :title="t('common.cancel')">✗</button>
          </div>
        </div>

        <div v-if="loading && !isCreating" class="loading-row">
          <div class="loading-text">{{ t('list.loading') }}</div>
        </div>
        <div v-else-if="items.length === 0 && !isCreating && !isEditing" class="empty-row">
          <div class="empty-text">{{ t('list.emptyData', { type: itemTypeLabel }) }}</div>
        </div>
        <div
          v-else
          v-for="item in filteredItems"
          :key="item.id"
          :data-item-id="item.id"
          :data-bug-id="item.id"
          class="table-row"
          :class="{
            selected: selectedItems.includes(item.id),
            'item-new': isNewItem(item.id),
            'editing-row': isEditing && editingItem?.id === item.id
          }"
          @click="handleRowClick(item, $event)"
        >
          <div class="row-checkbox">
            <input
              v-if="isEditing && editingItem?.id === item.id"
              type="checkbox"
              disabled
              style="opacity: 0.3"
            />
            <input
              v-else
              type="checkbox"
              :checked="selectedItems.includes(item.id)"
              @change="emit('toggleSelection', item.id)"
              @click.stop
            />
          </div>
          <div class="row-title">
            <!-- 编辑模式 -->
            <input
              v-if="isEditing && editingItem?.id === item.id"
              ref="editInputRef"
              v-model="editingTitle"
              type="text"
              class="create-input"
              :placeholder="t('cardCreate.titlePlaceholder')"
              @keyup.enter="confirmEdit"
              @keyup.esc="cancelEdit"
              @click.stop
            />
            <!-- 普通模式 -->
            <template v-else>
              <span class="card-title">{{ rowDisplayTitle(item) }}</span>
              <span v-if="isNewItem(item.id)" class="new-badge">{{ t('list.newPending') }}</span>
            </template>
          </div>
          <div class="row-status">
            <!-- 编辑模式 -->
            <select
              v-if="isEditing && editingItem?.id === item.id"
              v-model="editingType"
              class="type-select"
              @click.stop
            >
              <option value="bug">{{ t('list.types.bug') }}</option>
              <option value="badcase">{{ t('list.types.badcase') }}</option>
              <option value="testcase">{{ t('list.types.testCase') }}</option>
            </select>
            <!-- 普通模式 - 点击进入该类型列表，支持复制 -->
            <span v-else class="type-badge" :class="item.type" @click.stop>{{ getTypeText(item.type) }}</span>
          </div>
          <div class="row-date">
            <span class="date-text">{{ formatDate(item.created_at) }}</span>
          </div>
          <div class="row-actions" @click.stop>
            <!-- 编辑模式 -->
            <template v-if="isEditing && editingItem?.id === item.id">
              <button class="btn-icon-confirm" @click="confirmEdit" :disabled="!editingTitle.trim()" :title="t('common.confirm')">✓</button>
              <button class="btn-icon-cancel" @click="cancelEdit" :title="t('common.cancel')">✗</button>
            </template>
            <!-- 普通模式 -->
            <button v-else class="btn-icon-edit" :title="t('common.edit')" @click="startEdit(item)">✏️</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'

export default {
  name: 'CardPanel',
  props: {
    // 标题相关
    title: { type: String, default: '' },
    showHeader: { type: Boolean, default: true },
    
    // 数据
    items: { type: Array, default: () => [] },
    total: { type: Number, default: 0 },
    loading: { type: Boolean, default: false },
    selectedItems: { type: Array, default: () => [] },
    selectAll: { type: Boolean, default: false },
    
    // 筛选
    searchText: { type: String, default: '' },
    selectedStatus: { type: String, default: '' },
    
    // 类型
    itemType: { type: String, default: 'card' }, // badcase, bug, test_case, card
    
    // 新建卡片回调
    onQuickCreate: { type: Function, default: null },
    
    // 编辑卡片回调
    editItem: { type: Function, default: null },
    
    // 快速更新卡片回调（行内编辑）
    onQuickUpdate: { type: Function, default: null },
  },
  emits: ['edit', 'delete', 'refresh', 'search', 'toggleSelectAll', 'toggleSelection', 'update:searchText', 'quickCreate', 'create', 'quickUpdate', 'openTypeList'],
  setup(props, { emit }) {
    const { t } = useI18n()
    
    // 新建状态
    const isCreating = ref(false)
    const newCardTitle = ref('')
    const newCardType = ref('bug') // 默认类型为 bug
    const createInputRef = ref(null)
    const newlyCreatedIds = ref(new Set())
    
    // 编辑状态
    const isEditing = ref(false)
    const editingItem = ref(null)
    const editingTitle = ref('')
    const editingType = ref('bug')
    const editInputRef = ref(null)
    
    // 类型筛选状态
    const currentTypeFilter = ref('') // '' 表示总览，其他值为具体类型
    
    // 根据类型筛选的卡片列表
    const filteredItems = computed(() => {
      if (!currentTypeFilter.value) {
        return props.items
      }
      return props.items.filter(item => item.type === currentTypeFilter.value)
    })
    
    // 清除类型筛选，返回总览
    const clearTypeFilter = () => {
      currentTypeFilter.value = ''
    }
    
    const itemTypeLabel = computed(() => {
      if (props.itemType === 'bug') return t('list.types.bug')
      if (props.itemType === 'test_case') return t('list.types.testCase')
      if (props.itemType === 'card') return t('list.types.card')
      return t('list.types.badcase')
    })
    
    const getTypeText = (type) => {
      const typeMap = {
        'bug': t('list.types.bug'),
        'badcase': t('list.types.badcase'),
        'testcase': t('list.types.testCase'),
        'card': t('list.types.card')
      }
      return typeMap[type] || type || '—'
    }
    
    const formatDate = (dateStr) => {
      if (!dateStr) return '—'
      return new Date(dateStr).toLocaleDateString()
    }

    /** 卡片列表首列：统一展示「卡片标题」；testcase 若 title 未同步则用 remark/description 兜底 */
    const rowDisplayTitle = (item) => {
      if (!item) return '—'
      const raw = item.title != null ? String(item.title).trim() : ''
      if (raw) return raw
      const ty = (item.type || '').toString().toLowerCase()
      if (ty === 'testcase') {
        const rm = item.remark != null ? String(item.remark).trim() : ''
        if (rm) return rm.length > 200 ? `${rm.slice(0, 200)}…` : rm
        const desc = item.description != null ? String(item.description).trim() : ''
        if (desc) return desc.length > 200 ? `${desc.slice(0, 200)}…` : desc
      }
      return '—'
    }
    
    const isNewItem = (itemId) => {
      return newlyCreatedIds.value.has(itemId)
    }
    
    // 开始行内编辑
    const startEdit = async (item) => {
      console.log('[CardPanel] startEdit 被调用, item:', item)
      editingItem.value = item
      editingTitle.value = item.title || ''
      editingType.value = item.type || 'bug'
      isEditing.value = true
      await nextTick()
      // editInputRef 在 v-for 中是数组
      const inputEl = Array.isArray(editInputRef.value) ? editInputRef.value[0] : editInputRef.value
      if (inputEl) {
        inputEl.focus()
        inputEl.select()
      }
    }
    
    // 确认编辑
    const confirmEdit = async () => {
      const title = editingTitle.value.trim()
      if (!title || !editingItem.value) return
      
      try {
        const updateData = {
          id: editingItem.value.id,
          title: title,
          type: editingType.value
        }
        
        console.log('[CardPanel] confirmEdit - editingType:', editingType.value)
        console.log('[CardPanel] confirmEdit - updateData:', updateData)
        
        // 调用父组件的快速更新方法
        if (props.onQuickUpdate) {
          await props.onQuickUpdate(updateData)
        } else {
          emit('quickUpdate', updateData)
        }
      } catch (e) {
        console.error('更新卡片失败:', e)
        alert(t('common.unknownError'))
      } finally {
        cancelEdit()
      }
    }
    
    // 取消编辑
    const cancelEdit = () => {
      isEditing.value = false
      editingItem.value = null
      editingTitle.value = ''
      editingType.value = 'bug'
    }
    
    const startCreate = async () => {
      isCreating.value = true
      newCardTitle.value = ''
      newCardType.value = 'bug' // 重置为默认类型
      await nextTick()
      const inputEl = Array.isArray(createInputRef.value) ? createInputRef.value[0] : createInputRef.value
      if (inputEl) {
        inputEl.focus()
      }
    }
    
    const confirmCreate = async () => {
      const title = newCardTitle.value.trim()
      if (!title) return
      
      try {
        // 调用父组件的快速创建方法，传递标题和类型
        if (props.onQuickCreate) {
          await props.onQuickCreate(title, newCardType.value)
        } else {
          emit('quickCreate', { title, type: newCardType.value })
        }
        
        // 添加到新建ID集合，用于显示新标记
        // 延迟等待API返回真实ID
      } catch (e) {
        console.error('创建卡片失败:', e)
        alert(t('common.unknownError'))
      } finally {
        isCreating.value = false
        newCardTitle.value = ''
      }
    }
    
    const cancelCreate = () => {
      isCreating.value = false
      newCardTitle.value = ''
      newCardType.value = 'bug'
    }
    
    const handleCreateBlur = (e) => {
      // 延迟检查，因为可能点击的是确认/取消按钮
      setTimeout(() => {
        if (isCreating.value && !newCardTitle.value.trim()) {
          cancelCreate()
        }
      }, 150)
    }
    
    const handleRowClick = (item, e) => {
      if (e.button !== 0) return
      const el = e?.target
      if (el && typeof el.closest === 'function') {
        // 点击 checkbox 或操作按钮区域不处理
        if (el.closest('.row-checkbox') || el.closest('.row-actions')) return
      }
      // 点击卡片任意空白处，进入该类型的列表
      emit('openTypeList', item.type, item.title, item.id)
    }
    
    const batchDeleteSelected = async () => {
      const ids = [...props.selectedItems]
      if (!ids.length) return
      
      if (!confirm(t('list.batchDeleteConfirm', { n: ids.length, type: itemTypeLabel.value }))) return
      
      try {
        emit('batchDelete', ids)
      } catch (e) {
        console.error('批量删除异常:', e)
        alert(t('list.batchDeleteFail', { msg: e?.message || t('common.unknownError') }))
      }
    }
    
    // 添加新建ID到集合
    const addNewlyCreatedId = (id) => {
      newlyCreatedIds.value.add(id)
      // 3秒后移除标记
      setTimeout(() => {
        newlyCreatedIds.value.delete(id)
      }, 3000)
    }
    
    return { 
      t, 
      props,
      itemTypeLabel, 
      getTypeText, 
      formatDate,
      rowDisplayTitle,
      handleRowClick,
      startEdit,
      startCreate,
      confirmCreate,
      cancelCreate,
      handleCreateBlur,
      isCreating,
      newCardTitle,
      newCardType,
      createInputRef,
      isNewItem,
      batchDeleteSelected,
      emit,
      addNewlyCreatedId,
      // 类型筛选
      currentTypeFilter,
      filteredItems,
      clearTypeFilter,
      // 编辑相关
      isEditing,
      editingItem,
      editingTitle,
      editingType,
      editInputRef,
      confirmEdit,
      cancelEdit,
    }
  }
}
</script>

<style scoped>
.card-list-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.content-header {
  padding: 20px 24px;
  border-bottom: 1px solid #e9ecef;
}

.content-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.back-btn {
  padding: 4px 12px;
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.back-btn:hover {
  background: #357abd;
}

.type-filter-label {
  color: #4a90e2;
}

.completion-rate {
  font-size: 14px;
  color: #666;
  background: #f8f9fa;
  padding: 4px 8px;
  border-radius: 4px;
}

.content-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #e9ecef;
  background: #f8f9fa;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.quick-create-btn {
  padding: 6px 10px;
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.quick-create-btn:hover {
  background: #357abd;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.search-input-container {
  position: relative;
  display: flex;
  align-items: center;
}

.search-input {
  width: 200px;
  padding: 6px 12px 6px 32px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.search-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
}

.search-input-container .search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 12px;
  color: #999;
  pointer-events: none;
}

.filter-dropdown {
  position: relative;
}

.filter-select {
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  background: white;
  color: #333;
  cursor: pointer;
  min-width: 120px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.filter-select:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
}

.filter-select:hover {
  border-color: #bbb;
}

.refresh-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.refresh-btn:hover {
  background: #e9ecef;
}

.card-table {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.table-header {
  display: grid;
  grid-template-columns: 40px 2fr 1fr 1fr 100px;
  gap: 16px;
  padding: 12px 24px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  font-size: 12px;
  font-weight: 600;
  color: #666;
}

.table-body {
  flex: 1;
  overflow-y: auto;
}

.table-row {
  display: grid;
  grid-template-columns: 40px 2fr 1fr 1fr 100px;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid #f0f0f0;
  align-items: center;
  cursor: default;
  transition: background-color 0.2s;
  font-size: 12px;
}

.creating-row {
  background: #fffbe6;
  border-bottom: 2px solid #faad14;
}

.editing-row {
  background: #e6f7ff;
  border-bottom: 2px solid #1890ff;
}

.edit-indicator {
  font-size: 14px;
}

.item-new {
  background: #e6f7ff;
}

.table-row .row-title,
.table-row .row-status,
.table-row .row-date {
  cursor: default;
  min-width: 0;
}

.table-row .card-title,
.table-row .date-text,
.table-row .status-badge {
  cursor: text;
  user-select: text;
}

.table-row .row-checkbox,
.table-row .row-actions {
  user-select: none;
  cursor: default;
}

.table-row:hover {
  background: #f8f9fa;
}

.table-row.selected {
  background: #e3f2fd;
}

/* 与 grep/modify 列表定位一致：对话区点击跳转后的高亮动画 */
.table-row.highlight-row {
  animation: card-highlight-row-pulse 3s ease-in-out;
}

@keyframes card-highlight-row-pulse {
  0%,
  100% {
    background: #f8f9fa;
  }
  30% {
    background: #fff3cd;
    box-shadow: inset 4px 0 0 #ffc107;
  }
  60% {
    background: #fff8e1;
  }
}

.table-row.highlight-flash {
  animation: card-highlight-pulse 2s ease-in-out;
}

@keyframes card-highlight-pulse {
  0%,
  100% {
    background: #f8f9fa;
  }
  25% {
    background: #fff3cd;
    box-shadow: 0 0 10px rgba(255, 193, 7, 0.5);
  }
  50% {
    background: #ffc107;
  }
  75% {
    background: #fff3cd;
    box-shadow: 0 0 10px rgba(255, 193, 7, 0.5);
  }
}

.row-checkbox,
.header-checkbox {
  display: flex;
  align-items: center;
}

.row-title,
.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.row-status,
.header-status,
.row-date,
.header-date {
  display: flex;
  align-items: center;
}

.card-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.new-badge {
  font-size: 10px;
  padding: 2px 6px;
  background: #52c41a;
  color: white;
  border-radius: 4px;
  white-space: nowrap;
}

.new-indicator {
  font-size: 14px;
}

.create-input {
  width: 100%;
  padding: 6px 12px;
  border: 2px solid #faad14;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
  background: white;
}

.create-input:focus {
  border-color: #fa8c16;
  box-shadow: 0 0 0 2px rgba(250, 173, 20, 0.2);
}

.type-select {
  width: 100%;
  padding: 4px 8px;
  border: 1px solid #faad14;
  border-radius: 4px;
  font-size: 12px;
  background: white;
  cursor: pointer;
  outline: none;
}

.type-select:focus {
  border-color: #fa8c16;
  box-shadow: 0 0 0 2px rgba(250, 173, 20, 0.2);
}

.status-badge {
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  background: #d4edda;
  color: #155724;
  white-space: nowrap;
}

.status-badge.new {
  background: #e6f7ff;
  color: #1890ff;
}

.status-badge.not_badcase {
  background: #e2e3e5;
  color: #383d41;
}

.row-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.btn-icon-edit,
.btn-icon-confirm,
.btn-icon-cancel {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: background-color 0.2s;
}

.btn-icon-edit:hover {
  background: #e9ecef;
}

.btn-icon-confirm {
  color: #52c41a;
}

.btn-icon-confirm:hover:not(:disabled) {
  background: #d9f7be;
}

.btn-icon-confirm:disabled {
  color: #d9d9d9;
  cursor: not-allowed;
}

.btn-icon-cancel {
  color: #ff4d4f;
}

.btn-icon-cancel:hover {
  background: #fff1f0;
}

.loading-row,
.empty-row {
  padding: 24px;
  color: #666;
  font-size: 12px;
}

.empty-row {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.batch-delete-btn {
  padding: 6px 12px;
  background: #ef4444;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.batch-delete-btn:hover {
  background: #dc2626;
  transform: translateY(-1px);
}
</style>
