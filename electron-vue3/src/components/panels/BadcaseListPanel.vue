<template>
  <div class="badcase-list-panel">
    <!-- 多 Tab 工作区下顶栏已承载上下文，不再保留面包屑与 x/y 计数条，避免大块留白 -->
    <div v-if="showLongBreadcrumb" class="content-header">
      <div class="content-title">
        <span>{{ generateBreadcrumb() }}</span>
        <span class="completion-rate">{{ filteredBadcases.length }}/{{ totalBadcases }}</span>
      </div>
    </div>

    <div class="content-toolbar">
      <div class="toolbar-left">
        <button class="quick-create-btn" @click="handleCreateClick">
          {{ t('list.quickCreate', { type: listTypeLabel }) }}
        </button>
      </div>

      <div class="toolbar-right">
        <div class="search-input-container">
          <input
            type="text"
            :value="searchText"
            :placeholder="t('list.searchPlaceholder')"
            class="search-input"
            @input="(e) => updateSearchText(e.target.value)"
            @keyup.enter="applyFilters"
          />
          <span class="search-icon">🔍</span>
        </div>

        <div class="filter-dropdown">
          <select :value="selectedAssignee" @change="(e) => updateSelectedAssignee(e.target.value)" class="filter-select">
            <option value="">{{ t('list.assigneeAll') }}</option>
            <option value="mine">{{ t('list.assigneeMine') }}</option>
            <option v-for="member in projectMembers" :key="member.id" :value="member.id">
              {{ member.name }}
            </option>
          </select>
        </div>

        <div class="filter-dropdown">
          <select :value="selectedStatus" @change="(e) => updateSelectedStatus(e.target.value)" class="filter-select">
            <option value="">{{ t('list.statusAll') }}</option>
            <option value="new">{{ t('list.statusNew') }}</option>
            <option value="pending">{{ t('list.statusPending') }}</option>
            <option value="resolved">{{ t('list.statusResolved') }}</option>
            <option value="close">{{ t('list.statusClosed') }}</option>
            <option value="hold">{{ t('list.statusHold') }}</option>
            <option value="reopen">{{ t('list.statusReopen') }}</option>
            <option value="not_badcase">{{ t('list.statusNotType', { type: listTypeLabel }) }}</option>
          </select>
        </div>

        <button class="refresh-btn" :disabled="badcaseLoading" @click="refreshBadcases">🔄</button>
        <button
          v-if="selectedTasks && selectedTasks.length > 0"
          class="batch-delete-btn"
          @click.stop="batchDeleteSelected"
          :title="t('list.batchDeleteTitle', { n: selectedTasks.length })"
        >
          {{ t('list.batchDelete', { n: selectedTasks.length }) }}
        </button>
      </div>
    </div>

    <div class="task-table">
      <div class="table-header">
        <div class="header-checkbox">
          <input type="checkbox" :checked="selectAll" @change="toggleSelectAll" />
        </div>
        <div class="header-title">{{ t('list.colTitle', { type: listTypeLabel }) }}</div>
        <div class="header-type">{{ t('list.colType') }}</div>
        <div class="header-status">{{ t('list.colStatus') }}</div>
        <div class="header-assignee">{{ t('list.colAssignee') }}</div>
        <div class="header-date">{{ t('list.colCreated') }}</div>
        <div class="header-actions">{{ t('list.colActions') }}</div>
      </div>

      <div class="table-body">
        <div v-if="badcaseLoading" class="loading-row">
          <div class="loading-text">{{ t('list.loading') }}</div>
        </div>
        <template v-else>
          <!-- 待确认新建（create 沙箱）：暗绿显示新值，✓ 采纳 ✗ 拒绝 -->
          <div
            v-for="pc in (pendingCreates || [])"
            :key="pc?.tempId"
            :data-create-id="pc?.tempId"
            class="table-row pending-create-row"
            @click.stop
          >
            <div class="row-checkbox"></div>
            <div class="row-title">
              <SelectableTitleTip
                v-if="pc.displayDiff?.title"
                class="field-diff-inline create-pending-diff"
                :text="pc.displayDiff.title.new"
              >
                <span class="new-value-inline create-new-only">{{ pc.displayDiff.title.new }}</span>
              </SelectableTitleTip>
              <SelectableTitleTip
                v-else
                class="badcase-title create-new-only"
                :text="pc.preview?.title || ''"
              >{{ pc.preview?.title || t('list.newPending') }}</SelectableTitleTip>
            </div>
            <div class="row-type">
              <span class="type-badge" :class="currentPlanType">{{ listTypeLabel }}</span>
            </div>
            <div class="row-status">
              <div v-if="pc.displayDiff?.status" class="field-diff-inline create-pending-diff">
                <span class="new-value-inline create-new-only">{{ pc.displayDiff.status.new }}</span>
              </div>
              <span
                v-else-if="pc.preview?.status"
                class="status-badge"
                :class="pc.preview.status"
              >{{ getBadcaseStatusText(pc.preview.status) }}</span>
              <span v-else class="status-badge">—</span>
            </div>
            <div class="row-assignee">
              <div v-if="pc.displayDiff?.assignee" class="field-diff-inline create-pending-diff">
                <span class="new-value-inline create-new-only">{{ getAssigneeDisplayText(pc.displayDiff.assignee.new) }}</span>
              </div>
              <span v-else class="assignee-text">{{ getAssigneeDisplayText(pc.preview?.assignee_id) }}</span>
            </div>
            <div class="row-date"><span class="date-text">{{ t('list.pendingConfirm') }}</span></div>
            <div
              v-if="!pc?.executed && confirmCreate && cancelCreate && isLastInCreateCluster(pc?.tempId)"
              class="row-actions"
              @click.stop
            >
              <span v-if="getCreateClusterSize(pc?.tempId) > 1" class="batch-count">{{ t('common.nItems', { n: getCreateClusterSize(pc?.tempId) }) }}</span>
              <button class="btn-icon-approve" :title="t('list.approveCreate')" @click="confirmConsecutiveCreateGroup(pc?.tempId)">✓</button>
              <button class="btn-icon-reject" :title="t('list.reject')" @click="cancelConsecutiveCreateGroup(pc?.tempId)">✗</button>
            </div>
          </div>
          <div v-if="filteredBadcases.length === 0 && !(pendingCreates || []).length" class="empty-row">
            <div class="empty-text">{{ t('list.emptyData', { type: listTypeLabel }) }}</div>
          </div>
        </template>
        <template v-if="!badcaseLoading">
        <!-- data-bug-id 必须为源表主键（Bug/BadCase/TestCase id）。同一 card 下多行若用 card_id 会重复，grep/高亮永远命中首行 -->
        <div
          v-for="badcase in ((filteredBadcases || []).filter(b => b && b.id))"
          :key="badcase.id"
          :data-bug-id="badcase.id"
          :data-card-id="badcase.card_id ?? badcase.cardId ?? ''"
          class="table-row"
          :class="{
            selected: selectedTasks.includes(badcase.id),
            'pending-delete-row': pendingModifications[badcase.id]?._pendingDelete,
            'pending-modify': rowHasPendingModify(badcase)
          }"
          :title="t('common.copyRowHint')"
          @mousedown="onRowMouseDown"
          @click="handleRowClick(badcase, $event)"
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
            <SelectableTitleTip
              v-if="modifyPendingOverlay(badcase)?.title"
              class="field-diff-inline"
              :text="`${modifyPendingOverlay(badcase).title.old} → ${modifyPendingOverlay(badcase).title.new}`"
            >
              <span class="old-value-inline">{{ (modifyPendingOverlay(badcase).title.old || '').trim() || t('chat.notSet') }}</span>
              <span class="new-value-inline">{{ modifyPendingOverlay(badcase).title.new }}</span>
            </SelectableTitleTip>
            <SelectableTitleTip
              v-else
              class="badcase-title"
              :text="badcase.title"
            >{{ badcase.title }}</SelectableTitleTip>
          </div>
          <div class="row-type">
            <span class="type-badge" :class="currentPlanType">{{ listTypeLabel }}</span>
          </div>
          <div class="row-status">
            <div v-if="modifyPendingOverlay(badcase)?.status" class="field-diff-inline">
              <span class="old-value-inline">{{ getBadcaseStatusText(pendingStatusOldForRow(badcase)) }}</span>
              <span class="new-value-inline">{{ getBadcaseStatusText(modifyPendingOverlay(badcase).status.new) }}</span>
            </div>
            <span v-else class="status-badge" :class="badcase.status">{{ getBadcaseStatusText(badcase.status) }}</span>
          </div>
          <div class="row-assignee">
            <div v-if="modifyPendingOverlay(badcase)?.assignee" class="field-diff-inline">
              <span class="old-value-inline">{{ getAssigneeDisplayText(modifyPendingOverlay(badcase).assignee.old) }}</span>
              <span class="new-value-inline">{{ getAssigneeDisplayText(modifyPendingOverlay(badcase).assignee.new) }}</span>
            </div>
            <span v-else class="assignee-text">{{ getAssigneeDisplayText(badcase.assignee) }}</span>
          </div>
          <div class="row-date">
            <span class="date-text">{{ new Date(badcase.created_at).toLocaleDateString() }}</span>
          </div>

          <div
            v-if="pendingModifications[badcase.id]?._pendingDelete || modifyPendingOverlay(badcase)"
            class="row-actions"
            @click.stop
          >
            <template v-if="pendingModifications[badcase.id]?._pendingDelete">
              <template v-if="isLastInConsecutiveDeleteGroup(badcase.id)">
                <span v-if="getConsecutiveDeleteGroupSize(badcase.id) > 1" class="batch-count">{{ t('common.nItems', { n: getConsecutiveDeleteGroupSize(badcase.id) }) }}</span>
                <button class="btn-icon-approve" :title="t('list.approve')" @click="confirmConsecutiveDeleteGroup(badcase.id)">✓</button>
                <button class="btn-icon-reject" :title="t('list.cancelAction')" @click="cancelConsecutiveDeleteGroup(badcase.id)">✗</button>
              </template>
            </template>
            <template v-else>
              <template v-if="isLastInConsecutiveGroup(modifyPendingMapKey(badcase))">
                <span v-if="getConsecutiveGroupSize(modifyPendingMapKey(badcase)) > 1" class="batch-count">{{ t('common.nItems', { n: getConsecutiveGroupSize(modifyPendingMapKey(badcase)) }) }}</span>
                <button class="btn-icon-approve" :title="t('list.approve')" @click="confirmModify(modifyPendingMapKey(badcase))">✓</button>
                <button class="btn-icon-reject" :title="t('list.cancelAction')" @click="cancelModify(modifyPendingMapKey(badcase))">✗</button>
              </template>
            </template>
          </div>
        </div>
        </template>
      </div>
    </div>

    <div v-if="showPagination" class="list-pagination">
      <button
        type="button"
        class="pagination-btn"
        :disabled="badcaseLoading || page <= 1"
        @click="$emit('update:page', page - 1)"
      >
        {{ t('list.paginationPrev') }}
      </button>
      <span class="pagination-info">{{ t('list.paginationShort', { current: page, total: totalPages }) }}</span>
      <span class="pagination-total">{{ t('list.paginationTotal', { n: totalBadcases }) }}</span>
      <button
        type="button"
        class="pagination-btn"
        :disabled="badcaseLoading || page >= totalPages"
        @click="$emit('update:page', page + 1)"
      >
        {{ t('list.paginationNext') }}
      </button>
    </div>
  </div>
</template>

<script>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { deleteBug, deleteBadcase, deleteTestCase } from '../../api.js'
import SelectableTitleTip from '../SelectableTitleTip.vue'
export default {
  name: 'BadcaseListPanel',
  components: { SelectableTitleTip },
  props: {
    // header（多标签工作区下由顶栏 Tab 展示计划名，可关闭长面包屑）
    generateBreadcrumb: { type: Function, default: () => () => [] },
    showLongBreadcrumb: { type: Boolean, default: true },
    currentPlanType: { type: String, default: 'badcase' },
    totalBadcases: { type: Number, default: 0 },
    page: { type: Number, default: 1 },
    pageSize: { type: Number, default: 20 },

    // filters
    searchText: { type: String, default: '' },
    selectedAssignee: { type: [String, Number], default: '' },
    selectedStatus: { type: String, default: '' },
    projectMembers: { type: Array, default: () => [] },
    applyFilters: { type: Function, default: () => {} },
    refreshBadcases: { type: Function, default: () => {} },

    // table
    badcaseLoading: { type: Boolean, default: false },
    filteredBadcases: { type: Array, default: () => [] },
    selectedTasks: { type: Array, default: () => [] },
    selectAll: { type: Boolean, default: false },
    toggleSelectAll: { type: Function, default: () => {} },
    toggleTaskSelection: { type: Function, default: () => {} },
    // 兼容：历史上叫 editBadcase，但实际上适用于 BadCase/Bug/TestCase
    editBadcase: { type: Function, required: false, default: null },
    editItem: { type: Function, required: false, default: null },
    pendingModifications: { type: Object, default: () => ({}) },
    isLastInConsecutiveGroup: { type: Function, default: () => false },
    getConsecutiveGroupSize: { type: Function, default: () => 1 },
    confirmModify: { type: Function, default: () => {} },
    cancelModify: { type: Function, default: () => {} },
    confirmDelete: { type: Function, default: () => {} },
    isLastInConsecutiveDeleteGroup: { type: Function, default: () => true },
    getConsecutiveDeleteGroupSize: { type: Function, default: () => 1 },
    confirmConsecutiveDeleteGroup: { type: Function, default: () => {} },
    cancelConsecutiveDeleteGroup: { type: Function, default: () => {} },
    getBadcaseStatusText: { type: Function, default: (s) => s },
    getAssigneeDisplayText: { type: Function, default: (a) => a },

    // actions
    createNewBadcase: { type: Function, default: () => {} },
    /** 待确认新建（来自对话 create 沙箱） */
    pendingCreates: { type: Array, default: () => [] },
    confirmCreate: { type: Function, default: null },
    cancelCreate: { type: Function, default: null },
    isLastInCreateCluster: { type: Function, default: () => true },
    getCreateClusterSize: { type: Function, default: () => 1 },
    confirmConsecutiveCreateGroup: { type: Function, default: null },
    cancelConsecutiveCreateGroup: { type: Function, default: null }
  },
  emits: ['update:searchText', 'update:selectedAssignee', 'update:selectedStatus', 'update:page', 'openCreate'],
  setup(props, { emit }) {
    const { t } = useI18n()
    const listTypeLabel = computed(() => {
      if (props.currentPlanType === 'bug') return t('list.types.bug')
      if (props.currentPlanType === 'test_case') return t('list.types.testCase')
      return t('list.types.badcase')
    })

    const totalPages = computed(() => {
      const ps = Number(props.pageSize) || 20
      const tot = Number(props.totalBadcases) || 0
      return Math.max(1, Math.ceil(tot / ps))
    })

    const showPagination = computed(() => {
      const ps = Number(props.pageSize) || 20
      return (Number(props.totalBadcases) || 0) > ps
    })
    
    // 处理新建按钮点击
    const handleCreateClick = () => {
      emit('openCreate', props.currentPlanType)
    }
    
    return { t, listTypeLabel, totalPages, showPagination, handleCreateClick }
  },
  data() {
    return {
      /** 行上按下时记录，用于区分「划选复制」与「单击打开」 */
      _rowPress: null
    }
  },
  methods: {
    async batchDeleteSelected() {
      const ids = Array.isArray(this.selectedTasks) ? this.selectedTasks.slice() : []
      if (!ids.length) return

      if (!confirm(this.$t('list.batchDeleteConfirm', { n: ids.length, type: this.listTypeLabel }))) return

      try {
        const requests = ids.map((id) => {
          if (this.currentPlanType === 'bug') return deleteBug(id)
          if (this.currentPlanType === 'test_case') return deleteTestCase(id)
          return deleteBadcase(id)
        })

        const results = await Promise.allSettled(requests)
        const failed = results.filter(r => {
          if (r.status !== 'fulfilled') return true
          const ok = r.value?.data?.success === true
          return !ok
        }).length

        if (failed > 0) {
          alert(this.$t('list.batchDeletePartial', { failed }))
        } else {
          alert(this.$t('list.batchDeleteOk'))
        }
      } catch (e) {
        console.error('批量删除异常:', e)
        alert(this.$t('list.batchDeleteFail', { msg: e?.message || this.$t('common.unknownError') }))
      } finally {
        // refreshBadcases 会触发父组件重新拉取列表并清空 selectedTasks
        if (typeof this.refreshBadcases === 'function') {
          this.refreshBadcases()
        }
      }
    },
    handleEdit(id) {
      const fn = this.editItem || this.editBadcase
      if (typeof fn === 'function') fn(id)
    },
    /** target=card 时 pending 挂在 Card.id；Bug 行主键可能与 Card.id 数字相同，须排除 _target=card 以免卡片沙箱误投影到 Bug 子表 */
    modifyPendingOverlay(badcase) {
      const pm = this.pendingModifications
      const isCardLayer = (p) => p && String(p._target || '').toLowerCase() === 'card'
      const bidStr = badcase.id != null && badcase.id !== '' ? String(badcase.id).trim() : ''
      const a = bidStr && pm[bidStr] ? pm[bidStr] : pm[badcase.id]
      if (a && !a._pendingDelete && !isCardLayer(a)) return a
      const cidRaw = badcase.card_id ?? badcase.cardId
      const cidStr = cidRaw != null && cidRaw !== '' ? String(cidRaw).trim() : ''
      if (cidStr && /^\d+$/.test(cidStr)) {
        const c = pm[cidStr]
        if (c && !c._pendingDelete && !isCardLayer(c)) return c
      }
      return null
    },
    rowHasPendingModify(badcase) {
      const o = this.modifyPendingOverlay(badcase)
      return !!(o && !o._pendingDelete)
    },
    modifyPendingMapKey(badcase) {
      const pm = this.pendingModifications
      const isCardLayer = (p) => p && String(p._target || '').toLowerCase() === 'card'
      const bidStr = badcase.id != null && badcase.id !== '' ? String(badcase.id).trim() : ''
      if (bidStr && pm[bidStr] && !pm[bidStr]._pendingDelete && !isCardLayer(pm[bidStr])) return bidStr
      const cidRaw = badcase.card_id ?? badcase.cardId
      const cidStr = cidRaw != null && cidRaw !== '' ? String(cidRaw).trim() : ''
      if (
        cidStr &&
        /^\d+$/.test(cidStr) &&
        pm[cidStr] &&
        !pm[cidStr]._pendingDelete &&
        !isCardLayer(pm[cidStr])
      ) {
        return cidStr
      }
      return bidStr || String(badcase.id ?? '')
    },
    /** pending 里旧状态为空时，用当前行列表数据兜底，避免误显示「未设置」而库内实为 closed 等 */
    pendingStatusOldForRow(badcase) {
      const p = this.modifyPendingOverlay(badcase)?.status
      if (!p) return ''
      if (p.old != null && String(p.old).trim() !== '') return p.old
      return badcase.status
    },
    onRowMouseDown(e) {
      if (e.button !== 0) return
      const t = e.target
      if (typeof t.closest === 'function' && (t.closest('.row-checkbox') || t.closest('.row-actions'))) return
      this._rowPress = { x0: e.clientX, y0: e.clientY, moved: false }
      const move = (ev) => {
        if (!this._rowPress) return
        if (Math.hypot(ev.clientX - this._rowPress.x0, ev.clientY - this._rowPress.y0) > 6) {
          this._rowPress.moved = true
        }
      }
      const up = () => {
        document.removeEventListener('mousemove', move)
        document.removeEventListener('mouseup', up)
      }
      document.addEventListener('mousemove', move, { passive: true })
      document.addEventListener('mouseup', up, { once: true })
    },
    _hasTextSelection() {
      if (typeof window === 'undefined' || !window.getSelection) return false
      return !!String(window.getSelection().toString()).trim()
    },
    /** 单击打开详情；划选/拖拽复制时不打开（详情 Tab 由父组件按 id 去重） */
    handleRowClick(badcase, e) {
      if (e.button !== 0) return
      const el = e?.target
      if (el && typeof el.closest === 'function') {
        if (el.closest('.row-checkbox') || el.closest('.row-actions')) return
      }
      if (this._rowPress?.moved) {
        this._rowPress = null
        return
      }
      this._rowPress = null
      if (this._hasTextSelection()) return
      setTimeout(() => {
        if (this._hasTextSelection()) return
        this.handleEdit(badcase.id)
      }, 0)
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
  display: none;
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
  grid-template-columns: 40px 2fr 1fr 1fr 1fr 1fr 120px;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid #f0f0f0;
  align-items: center;
  cursor: default;
  transition: background-color 0.2s;
  font-size: 12px;
}

/* 列内空白处为箭头；仅文字节点为 I 形光标，便于划选复制 */
.table-row .row-title,
.table-row .row-type,
.table-row .row-status,
.table-row .row-assignee,
.table-row .row-date {
  cursor: default;
  min-width: 0;
}

.table-row .badcase-title,
.table-row .date-text,
.table-row .assignee-text,
.table-row .type-badge,
.table-row .status-badge,
.table-row .field-diff-inline,
.table-row .field-diff-inline span {
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

.table-row.pending-modify {
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
}

/* 与 VS Code / Cursor 删除行一致：左 #f14c4c 竖条 + rgba(255,0,0,.18) 底，正文保持默认色 */
.table-row.pending-delete-row {
  background: rgba(255, 0, 0, 0.18) !important;
  border-left: 4px solid #f14c4c;
}

.table-row.pending-delete-row:hover {
  background: rgba(255, 0, 0, 0.22) !important;
}

.table-row.pending-delete-row .badcase-title {
  text-decoration: line-through;
  text-decoration-color: rgba(0, 0, 0, 0.28);
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
  min-width: 0;
}

.table-row .badcase-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
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
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
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
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  background: #d4edda;
  color: #155724;
  white-space: nowrap;
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

.loading-row,
.empty-row {
  padding: 24px;
  color: #666;
  font-size: 12px;
}

/* 空状态：在表格可视区域居中显示 */
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

.list-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 10px 16px;
  padding: 12px 24px 16px;
  border-top: 1px solid #e9ecef;
  background: #fafbfc;
  font-size: 13px;
  color: #555;
}

.list-pagination .pagination-btn {
  padding: 6px 14px;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  color: #333;
}

.list-pagination .pagination-btn:hover:not(:disabled) {
  background: #f0f4f8;
  border-color: #b6c2cf;
}

.list-pagination .pagination-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.list-pagination .pagination-info {
  font-weight: 600;
  color: #333;
}

.list-pagination .pagination-total {
  color: #888;
  font-size: 12px;
}
</style>

