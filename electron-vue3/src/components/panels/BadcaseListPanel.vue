<template>
  <div class="badcase-list-panel">
    <div class="content-header">
      <div class="content-title">
        <span>{{ generateBreadcrumb() }}</span>
        <span class="completion-rate">{{ filteredBadcases.length }}/{{ totalBadcases }}</span>
      </div>
    </div>

    <div class="content-toolbar">
      <div class="toolbar-left">
        <button class="quick-create-btn" @click="createNewBadcase">
          +快速新建{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}
        </button>
      </div>

      <div class="toolbar-right">
        <div class="search-input-container">
          <input
            type="text"
            :value="searchText"
            placeholder="搜索标题或负责人..."
            class="search-input"
            @input="(e) => updateSearchText(e.target.value)"
            @keyup.enter="applyFilters"
          />
          <span class="search-icon">🔍</span>
        </div>

        <div class="filter-dropdown">
          <select :value="selectedAssignee" @change="(e) => updateSelectedAssignee(e.target.value)" class="filter-select">
            <option value="">全部负责人</option>
            <option value="mine">只看自己</option>
            <option v-for="member in projectMembers" :key="member.id" :value="member.id">
              {{ member.name }}
            </option>
          </select>
        </div>

        <div class="filter-dropdown">
          <select :value="selectedStatus" @change="(e) => updateSelectedStatus(e.target.value)" class="filter-select">
            <option value="">全部状态</option>
            <option value="new">新建</option>
            <option value="pending">待处理</option>
            <option value="resolved">已解决</option>
            <option value="close">已关闭</option>
            <option value="hold">暂停</option>
            <option value="reopen">重新打开</option>
            <option value="not_badcase">非{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}</option>
          </select>
        </div>

        <button class="refresh-btn" :disabled="badcaseLoading" @click="refreshBadcases">🔄</button>
        <button class="view-btn">📋</button>
        <span class="total-count">共{{ filteredBadcases.length }}条</span>
      </div>
    </div>

    <div class="task-table">
      <div class="table-header">
        <div class="header-checkbox">
          <input type="checkbox" :checked="selectAll" @change="toggleSelectAll" />
        </div>
        <div class="header-title">{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}标题</div>
        <div class="header-type">类型</div>
        <div class="header-status">状态</div>
        <div class="header-assignee">负责人</div>
        <div class="header-date">创建时间</div>
        <div class="header-actions">操作</div>
      </div>

      <div class="table-body">
        <div v-if="badcaseLoading" class="loading-row">
          <div class="loading-text">加载中...</div>
        </div>
        <div v-else-if="filteredBadcases.length === 0" class="empty-row">
          <div class="empty-text">暂无{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}数据</div>
        </div>
        <div
          v-else
          v-for="badcase in filteredBadcases"
          :key="badcase.id"
          :data-bug-id="badcase.id"
          class="table-row"
          :class="{
            selected: selectedTasks.includes(badcase.id),
            'pending-modify': pendingModifications[badcase.id]
          }"
          style="cursor: pointer;"
          @click="handleEdit(badcase.id)"
        >
          <div class="row-checkbox">
            <input
              type="checkbox"
              :checked="selectedTasks.includes(badcase.id)"
              @change="toggleTaskSelection(badcase.id)"
              @click.stop
            />
          </div>
          <div class="row-title">
            <div v-if="pendingModifications[badcase.id]?.title" class="field-diff-inline">
              <span class="old-value-inline">{{ pendingModifications[badcase.id].title.old }}</span>
              <span class="new-value-inline">{{ pendingModifications[badcase.id].title.new }}</span>
            </div>
            <span v-else class="badcase-title">{{ badcase.title }}</span>
          </div>
          <div class="row-type">
            <span class="type-badge" :class="currentPlanType">{{ currentPlanType === 'bug' ? 'Bug' : (currentPlanType === 'test_case' ? '测试用例' : 'BadCase') }}</span>
          </div>
          <div class="row-status">
            <div v-if="pendingModifications[badcase.id]?.status" class="field-diff-inline">
              <span class="old-value-inline">{{ pendingModifications[badcase.id].status.old }}</span>
              <span class="new-value-inline">{{ pendingModifications[badcase.id].status.new }}</span>
            </div>
            <span v-else class="status-badge" :class="badcase.status">{{ getBadcaseStatusText(badcase.status) }}</span>
          </div>
          <div class="row-assignee">
            <div v-if="pendingModifications[badcase.id]?.assignee" class="field-diff-inline">
              <span class="old-value-inline">{{ getAssigneeDisplayText(pendingModifications[badcase.id].assignee.old) }}</span>
              <span class="new-value-inline">{{ getAssigneeDisplayText(pendingModifications[badcase.id].assignee.new) }}</span>
            </div>
            <span v-else class="assignee-text">{{ getAssigneeDisplayText(badcase.assignee) }}</span>
          </div>
          <div class="row-date">
            <span class="date-text">{{ new Date(badcase.created_at).toLocaleDateString() }}</span>
          </div>

          <div v-if="pendingModifications[badcase.id]" class="row-actions" @click.stop>
            <button
              v-if="hasDetailFieldModifications(badcase.id)"
              class="btn-expand-detail"
              :title="expandedDetailRows.includes(badcase.id) ? '收起详情' : '展开详情'"
              @click="toggleDetailExpand(badcase.id)"
            >
              {{ expandedDetailRows.includes(badcase.id) ? '▼' : '▶' }}
            </button>
            <template v-if="isLastInConsecutiveGroup(badcase.id)">
              <span v-if="getConsecutiveGroupSize(badcase.id) > 1" class="batch-count">{{ getConsecutiveGroupSize(badcase.id) }}条</span>
              <button class="btn-icon-approve" title="确认" @click="confirmConsecutiveGroup(badcase.id)">✓</button>
              <button class="btn-icon-reject" title="取消" @click="cancelConsecutiveGroup(badcase.id)">✗</button>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'BadcaseListPanel',
  props: {
    // header
    generateBreadcrumb: { type: Function, required: true },
    currentPlanType: { type: String, default: 'badcase' },
    totalBadcases: { type: Number, default: 0 },

    // filters
    searchText: { type: String, default: '' },
    selectedAssignee: { type: [String, Number], default: '' },
    selectedStatus: { type: String, default: '' },
    projectMembers: { type: Array, default: () => [] },
    applyFilters: { type: Function, required: true },
    refreshBadcases: { type: Function, required: true },

    // table
    badcaseLoading: { type: Boolean, default: false },
    filteredBadcases: { type: Array, default: () => [] },
    selectedTasks: { type: Array, default: () => [] },
    selectAll: { type: Boolean, default: false },
    toggleSelectAll: { type: Function, required: true },
    toggleTaskSelection: { type: Function, required: true },
    // 兼容：历史上叫 editBadcase，但实际上适用于 BadCase/Bug/TestCase
    editBadcase: { type: Function, required: false, default: null },
    editItem: { type: Function, required: false, default: null },
    pendingModifications: { type: Object, default: () => ({}) },
    expandedDetailRows: { type: Array, default: () => [] },
    hasDetailFieldModifications: { type: Function, required: true },
    toggleDetailExpand: { type: Function, required: true },
    isLastInConsecutiveGroup: { type: Function, required: true },
    getConsecutiveGroupSize: { type: Function, required: true },
    confirmConsecutiveGroup: { type: Function, required: true },
    cancelConsecutiveGroup: { type: Function, required: true },
    getBadcaseStatusText: { type: Function, required: true },
    getAssigneeDisplayText: { type: Function, required: true },

    // actions
    createNewBadcase: { type: Function, required: true }
  },
  emits: ['update:searchText', 'update:selectedAssignee', 'update:selectedStatus'],
  methods: {
    handleEdit(id) {
      const fn = this.editItem || this.editBadcase
      if (typeof fn === 'function') fn(id)
    },
    updateSearchText(v) {
      this.$emit('update:searchText', v)
      this.applyFilters()
    },
    updateSelectedAssignee(v) {
      this.$emit('update:selectedAssignee', v)
      this.applyFilters()
    },
    updateSelectedStatus(v) {
      this.$emit('update:selectedStatus', v)
      this.applyFilters()
    }
  }
}
</script>

<style scoped>
/* 说明：原本这些样式在 ProjectDetail.vue 的 scoped 样式里。
   抽成 Panel 后，父组件 scoped 样式不会作用到子组件，所以需要迁移到 Panel 内。 */

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
  padding: 6px 12px;
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.2s;
  display: flex;
  align-items: center;
  gap: 4px;
}

.quick-create-btn:hover {
  background: #357abd;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 搜索输入框样式 */
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

/* 筛选下拉框样式 */
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

.refresh-btn,
.view-btn {
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

.refresh-btn:hover,
.view-btn:hover {
  background: #e9ecef;
}

.total-count {
  font-size: 13px;
  color: #666;
}

/* 任务表格 */
.task-table {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.table-header {
  display: grid;
  grid-template-columns: 40px 2fr 1fr 1fr 1fr 1fr 120px;
  gap: 16px;
  padding: 12px 24px;
  background: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  font-size: 13px;
  font-weight: 600;
  color: #666;
}

.table-body {
  flex: 1;
  overflow-y: auto;
}

.table-row {
  display: grid;
  grid-template-columns: 40px 2fr 1fr 1fr 1fr 1fr 120px;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid #f0f0f0;
  align-items: center;
  cursor: pointer;
  transition: background-color 0.2s;
}

.table-row:hover {
  background: #f8f9fa;
}

.table-row.selected {
  background: #e3f2fd;
}

.table-row.pending-modify {
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
}

/* Bug导航高亮动画 */
.table-row.highlight-flash {
  animation: highlight-pulse 2s ease-in-out;
}

@keyframes highlight-pulse {
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

.row-type,
.header-type,
.row-status,
.header-status,
.row-assignee,
.header-assignee {
  display: flex;
  align-items: center;
}

.type-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.type-badge.bug {
  background: #fff3cd;
  color: #856404;
}

.type-badge.test_request {
  background: #d1ecf1;
  color: #0c5460;
}

.type-badge.badcase {
  background: #e3f2fd;
  color: #1976d2;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  background: #d4edda;
  color: #155724;
}

.status-badge.not_badcase {
  background: #e2e3e5;
  color: #383d41;
}

.field-diff-inline {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.old-value-inline {
  background: #fef2f2;
  color: #991b1b;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  text-decoration: line-through;
  border: 1px solid #fecaca;
}

.new-value-inline {
  background: #f0fdf4;
  color: #166534;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid #bbf7d0;
}

.highlight-row {
  animation: highlight-pulse-2 2s ease-out;
  background-color: #fef3c7 !important;
}

@keyframes highlight-pulse-2 {
  0% {
    background-color: #fbbf24;
  }
  100% {
    background-color: transparent;
  }
}

.row-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.btn-icon-approve,
.btn-icon-reject {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-icon-approve {
  background: #10b981;
  color: white;
}

.btn-icon-approve:hover {
  background: #059669;
  transform: scale(1.1);
}

.btn-icon-reject {
  background: #ef4444;
  color: white;
}

.btn-icon-reject:hover {
  background: #dc2626;
  transform: scale(1.1);
}

.batch-count {
  font-size: 12px;
  font-weight: 600;
  color: #f59e0b;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: 10px;
  margin-right: 8px;
}

.btn-expand-detail {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
  background: white;
  color: #374151;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-expand-detail:hover {
  background: #f3f4f6;
}

.loading-row,
.empty-row {
  padding: 24px;
  color: #666;
  font-size: 13px;
}

/* 空状态：在表格可视区域居中显示 */
.empty-row {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}
</style>

