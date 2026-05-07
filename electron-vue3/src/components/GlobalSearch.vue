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
          placeholder="搜索卡片、详情..."
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
        <span>搜索中...</span>
      </div>

      <div v-else-if="!searchQuery" class="search-empty">
        <span>输入关键词搜索卡片和详情</span>
      </div>

      <div v-else-if="searchResults.length === 0" class="search-no-results">
        <span>未找到相关结果</span>
      </div>

      <div v-else class="results-container">
        <div
          v-for="(group, type) in groupedResults"
          :key="type"
          class="result-group"
        >
          <!-- 卡片分组标题 -->
          <div class="group-header" @click="toggleGroup(type)">
            <span class="group-icon">{{ getTypeIcon(type) }}</span>
            <span class="group-title">{{ getTypeLabel(type) }}</span>
            <span class="group-count">{{ group.length }}</span>
            <span class="group-arrow" :class="{ collapsed: collapsedGroups.includes(type) }">▼</span>
          </div>

          <!-- 卡片列表 -->
          <div v-if="!collapsedGroups.includes(type)" class="group-items">
            <div
              v-for="result in group"
              :key="`card-${result.id}`"
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
import { getProjectBadcases, getProjectBugs, getProjectTestCases, getProjectPlans, getProjectCards } from '../api'

const props = defineProps({
  projectId: { type: [String, Number, null], default: null },
  showClose: { type: Boolean, default: true }
})

const emit = defineEmits(['close', 'select-card', 'select-detail'])

// Refs
const searchInputRef = ref(null)
const resultsContainerRef = ref(null)

// State
const searchQuery = ref('')
const searchResults = ref([])
const loading = ref(false)
const collapsedGroups = ref([])

// Debounce timer
let searchTimer = null

// Methods
const handleSearch = () => {
  clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    return
  }

  searchTimer = setTimeout(async () => {
    loading.value = true
    try {
      const query = searchQuery.value.toLowerCase().trim()

      const pid = Number(props.projectId)
      if (!pid || Number.isNaN(pid)) {
        searchResults.value = []
        loading.value = false
        return
      }
      
      // 并行获取所有数据（按当前 projectId）
      const [plansRes, cardsRes, badcasesRes, bugsRes, testcasesRes] = await Promise.allSettled([
        getProjectPlans(pid).catch(() => ({ data: { data: [] } })),
        getProjectCards(pid).catch(() => ({ data: { data: [] } })),
        getProjectBadcases(pid, 1, 200).catch(() => ({ data: { data: [] } })),
        getProjectBugs(pid, 1, 200).catch(() => ({ data: { data: [] } })),
        getProjectTestCases(pid, 1, 200).catch(() => ({ data: { data: [] } }))
      ])

      const results = []

      // 处理 Plans（迭代计划）
      const plans = plansRes.value?.data?.data || []
      plans.forEach(item => {
        if ((item.title || item.name || '').toLowerCase().includes(query)) {
          results.push({
            type: 'plan',
            id: item.id,
            title: item.title || item.name || `Plan#${item.id}`,
            status: item.status || '',
            status_text: item.status_text || '',
            details: []
          })
        }
      })

      // 处理 Cards（卡片）
      const cards = cardsRes.value?.data?.data || []
      cards.forEach(item => {
        if ((item.title || '').toLowerCase().includes(query)) {
          results.push({
            type: 'card',
            id: item.id,
            title: item.title,
            status: item.status || '',
            status_text: item.status_text || '',
            details: item.details || []
          })
        }
        if (item.details && item.details.length > 0) {
          const matchedDetails = item.details.filter(d =>
            (d.description || '').toLowerCase().includes(query) ||
            (d.title || '').toLowerCase().includes(query)
          )
          if (matchedDetails.length > 0) {
            const alreadyAdded = results.some(r => r.type === 'card' && r.id === item.id)
            if (!alreadyAdded) {
              results.push({
                type: 'card',
                id: item.id,
                title: item.title,
                status: item.status || '',
                status_text: item.status_text || '',
                details: matchedDetails
              })
            }
          }
        }
      })

      // 处理 Badcase
      const badcases = badcasesRes.value?.data?.data || []
      badcases.forEach(item => {
        const details = []
        // 检查标题匹配
        if ((item.title || '').toLowerCase().includes(query)) {
          results.push({
            type: 'badcase',
            id: item.id,
            title: item.title,
            status: item.status || 'open',
            status_text: item.status_text || '',
            details: item.details || details
          })
        }
        // 检查详情匹配
        if (item.details && item.details.length > 0) {
          const matchedDetails = item.details.filter(d => 
            (d.description || '').toLowerCase().includes(query) ||
            (d.title || '').toLowerCase().includes(query)
          )
          if (matchedDetails.length > 0) {
            const alreadyAdded = results.some(r => r.type === 'badcase' && r.id === item.id)
            if (!alreadyAdded) {
              results.push({
                type: 'badcase',
                id: item.id,
                title: item.title,
                status: item.status || 'open',
                status_text: item.status_text || '',
                details: matchedDetails
              })
            }
          }
        }
      })

      // 处理 Bug
      const bugs = bugsRes.value?.data?.data || []
      bugs.forEach(item => {
        if ((item.title || '').toLowerCase().includes(query)) {
          results.push({
            type: 'bug',
            id: item.id,
            title: item.title,
            status: item.status || 'open',
            status_text: item.status_text || '',
            details: item.details || []
          })
        }
        if (item.details && item.details.length > 0) {
          const matchedDetails = item.details.filter(d => 
            (d.description || '').toLowerCase().includes(query) ||
            (d.title || '').toLowerCase().includes(query)
          )
          if (matchedDetails.length > 0) {
            const alreadyAdded = results.some(r => r.type === 'bug' && r.id === item.id)
            if (!alreadyAdded) {
              results.push({
                type: 'bug',
                id: item.id,
                title: item.title,
                status: item.status || 'open',
                status_text: item.status_text || '',
                details: matchedDetails
              })
            }
          }
        }
      })

      // 处理 TestCase
      const testcases = testcasesRes.value?.data?.data || []
      testcases.forEach(item => {
        if ((item.title || '').toLowerCase().includes(query)) {
          results.push({
            type: 'testcase',
            id: item.id,
            title: item.title,
            status: item.status || 'active',
            status_text: item.status_text || '',
            details: item.details || []
          })
        }
        if (item.details && item.details.length > 0) {
          const matchedDetails = item.details.filter(d => 
            (d.description || '').toLowerCase().includes(query) ||
            (d.title || '').toLowerCase().includes(query)
          )
          if (matchedDetails.length > 0) {
            const alreadyAdded = results.some(r => r.type === 'testcase' && r.id === item.id)
            if (!alreadyAdded) {
              results.push({
                type: 'testcase',
                id: item.id,
                title: item.title,
                status: item.status || 'active',
                status_text: item.status_text || '',
                details: matchedDetails
              })
            }
          }
        }
      })

      searchResults.value = results
    } catch (error) {
      console.error('搜索失败:', error)
      searchResults.value = []
    } finally {
      loading.value = false
    }
  }, 300)
}

const groupedResults = computed(() => {
  const groups = { bug: [], badcase: [], testcase: [] }
  searchResults.value.forEach(result => {
    if (groups[result.type]) {
      groups[result.type].push(result)
    }
  })
  return groups
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
  const icons = { bug: '🐛', badcase: '📋', testcase: '🧪' }
  return icons[type] || '📄'
}

const getTypeLabel = (type) => {
  const labels = { bug: 'Bug', badcase: 'BadCase', testcase: '测试用例' }
  return labels[type] || type
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
