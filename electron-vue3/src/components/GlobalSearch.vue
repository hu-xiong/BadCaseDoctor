<template>
  <div class="search-panel">
    <!-- 搜索头部 -->
    <div class="search-panel-header">
      <div class="search-input-wrapper">
        <span class="search-icon">🔍</span>
        <input
          ref="searchInputRef"
          v-model="searchQuery"
          type="text"
          class="search-input"
          :placeholder="t('globalSearch.placeholder')"
          @keydown.escape="handleClose"
          @input="handleSearch"
        />
        <button v-if="searchQuery" class="clear-btn" @click="clearSearch">✕</button>
      </div>
      <button v-if="showClose" class="close-btn" @click="handleClose">✕</button>
    </div>

    <!-- 搜索结果 -->
    <div class="search-panel-body" ref="resultsContainerRef">
      <div v-if="loading" class="search-loading">
        <span>{{ t('globalSearch.searching') }}</span>
      </div>

      <div v-else-if="!searchQuery" class="search-empty">
        <span>{{ t('globalSearch.emptyHint') }}</span>
      </div>

      <div v-else-if="searchResults.length === 0" class="search-no-results">
        <span>{{ t('globalSearch.noResults') }}</span>
      </div>

      <div v-else class="results-container">
        <div
          v-for="{ type, items } in groupedResultsToShow"
          :key="type"
          class="result-group"
        >
          <!-- 卡片分组标题 -->
          <div class="group-header" @click="toggleGroup(type)">
            <span class="group-icon">{{ getTypeIcon(type) }}</span>
            <span class="group-title">{{ getTypeLabel(type) }}</span>
            <span class="group-count">{{ items.length }}</span>
            <span class="group-arrow" :class="{ collapsed: collapsedGroups.includes(type) }">▼</span>
          </div>

          <!-- 卡片列表 -->
          <div v-if="!collapsedGroups.includes(type)" class="group-items">
            <div
              v-for="result in items"
              :key="`${type}-${result.type}-${result.id}`"
              class="result-card"
              @click="handleSelectCard(result)"
            >
              <div class="card-title">{{ result.title }}</div>
              <div class="card-meta">
                <span class="card-status" :class="`status-${result.status}`">{{ result.status_text || result.status }}</span>
              </div>

              <!-- 详情列表 -->
              <div
                v-if="result.details && result.details.length > 0"
                class="detail-items"
              >
                <div
                  v-for="detail in result.details"
                  :key="`detail-${detail.id}`"
                  class="result-detail"
                  @click.stop="handleSelectDetail(result, detail)"
                >
                  <span class="detail-icon">📝</span>
                  <span class="detail-title">{{ detail.title || detail.description }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { globalSearch } from '../api'

const { t } = useI18n()

const props = defineProps({
  projectId: { type: [String, Number, null], default: null },
  showClose: { type: Boolean, default: true }
})

const emit = defineEmits(['close', 'select-card', 'select-detail'])

/** 迭代卡片（Card）在侧边分组：与列表「类型」列一致 */
function cardRowGroupKey(cardType) {
  const t = (cardType || '').toString().toLowerCase()
  if (t === 'bug') return 'bug'
  if (t === 'badcase') return 'badcase'
  if (t === 'testcase' || t === 'test_case') return 'testcase'
  return 'card'
}

// Refs
const searchInputRef = ref(null)
const resultsContainerRef = ref(null)

// State
const searchQuery = ref('')
const searchResults = ref([])
const loading = ref(false)
const collapsedGroups = ref([])

// Debounce timer + 丢弃过期请求
let searchTimer = null
let searchSeq = 0

// Methods
const handleSearch = () => {
  clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    loading.value = false
    return
  }

  searchTimer = setTimeout(async () => {
    const pid = Number(props.projectId)
    if (!pid || Number.isNaN(pid)) {
      searchResults.value = []
      return
    }

    const qRaw = searchQuery.value.trim()
    const seq = ++searchSeq
    loading.value = true
    try {
      const res = await globalSearch(pid, qRaw, 30)
      if (seq !== searchSeq) return
      const body = res?.data
      searchResults.value = body?.results || []
    } catch (error) {
      if (seq !== searchSeq) return
      console.error('搜索失败:', error)
      searchResults.value = []
    } finally {
      if (seq === searchSeq) loading.value = false
    }
  }, 400)
}

const groupedResults = computed(() => {
  const groups = { plan: [], bug: [], badcase: [], testcase: [], card: [] }
  searchResults.value.forEach((result) => {
    if (result.type === 'plan') {
      groups.plan.push(result)
      return
    }
    if (result.type === 'card') {
      const gk = result.groupKey || cardRowGroupKey(result.cardType)
      if (gk === 'bug' || gk === 'badcase' || gk === 'testcase') {
        groups[gk].push(result)
      } else {
        groups.card.push(result)
      }
      return
    }
    if (groups[result.type]) {
      groups[result.type].push(result)
    }
  })
  return groups
})

/** 仅展示有命中条目的分组，隐藏计数为 0 的分类 */
const GROUP_DISPLAY_ORDER = ['plan', 'bug', 'badcase', 'testcase', 'card']
const groupedResultsToShow = computed(() => {
  const g = groupedResults.value
  return GROUP_DISPLAY_ORDER.filter((type) => (g[type] || []).length > 0).map((type) => ({
    type,
    items: g[type]
  }))
})

const toggleGroup = (type) => {
  const index = collapsedGroups.value.indexOf(type)
  if (index > -1) {
    collapsedGroups.value.splice(index, 1)
  } else {
    collapsedGroups.value.push(type)
  }
}

const clearSearch = () => {
  searchQuery.value = ''
  searchResults.value = []
  searchInputRef.value?.focus()
}

const handleClose = () => {
  emit('close')
}

const handleSelectCard = (card) => {
  emit('select-card', card)
}

const handleSelectDetail = (card, detail) => {
  emit('select-detail', { card, detail })
}

const getTypeIcon = (type) => {
  const icons = {
    plan: '📁',
    card: '🗂️',
    bug: '🐛',
    badcase: '📋',
    testcase: '🧪'
  }
  return icons[type] || '📄'
}

const getTypeLabel = (type) => {
  const key = `globalSearch.types.${type}`
  const label = t(key)
  return label === key ? type : label
}

// Focus input on mount
onMounted(() => {
  nextTick(() => {
    searchInputRef.value?.focus()
  })
})
</script>

<style scoped>
.search-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
}

.search-panel-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #e8e8e8;
  gap: 8px;
}

.search-input-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  background: #f5f5f5;
  border-radius: 6px;
  padding: 0 10px;
}

.search-icon {
  font-size: 14px;
  margin-right: 6px;
  color: #999;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 13px;
  padding: 8px 0;
  outline: none;
}

.search-input::placeholder {
  color: #999;
}

.clear-btn {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  padding: 2px 6px;
  font-size: 12px;
}

.clear-btn:hover {
  color: #666;
}

.close-btn {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  padding: 4px 8px;
  font-size: 14px;
}

.close-btn:hover {
  color: #333;
}

.search-panel-body {
  flex: 1;
  overflow-y: auto;
}

.search-loading,
.search-empty,
.search-no-results {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #999;
  font-size: 13px;
}

.results-container {
  padding: 8px;
}

.result-group {
  margin-bottom: 8px;
}

.group-header {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  background: #f8f9fa;
  border-radius: 6px;
  cursor: pointer;
  gap: 8px;
}

.group-header:hover {
  background: #e9ecef;
}

.group-icon {
  font-size: 14px;
}

.group-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: #333;
}

.group-count {
  font-size: 12px;
  color: #999;
  background: #fff;
  padding: 1px 6px;
  border-radius: 10px;
}

.group-arrow {
  font-size: 10px;
  color: #999;
  transition: transform 0.2s;
}

.group-arrow.collapsed {
  transform: rotate(-90deg);
}

.group-items {
  padding: 4px 0 4px 12px;
}

.result-card {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  margin-bottom: 4px;
}

.result-card:hover {
  background: #f5f5f5;
}

.card-title {
  font-size: 13px;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  margin-top: 4px;
}

.card-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #f6ffed;
  color: #52c41a;
}

.card-status.status-closed,
.card-status.status-resolved {
  background: #f5f5f5;
  color: #999;
}

.detail-items {
  margin-top: 6px;
  padding-left: 8px;
  border-left: 2px solid #e8e8e8;
}

.result-detail {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  gap: 6px;
}

.result-detail:hover {
  background: #e6f7ff;
}

.detail-icon {
  font-size: 12px;
}

.detail-title {
  font-size: 12px;
  color: #666;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
