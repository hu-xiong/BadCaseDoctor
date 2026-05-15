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
          placeholder="搜索迭代计划、卡片、BadCase、Bug、测试用例..."
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
        <span>输入关键词搜索迭代计划与工作内容</span>
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
import { getProjectBadcases, getProjectBugs, getProjectTestCases, getProjectPlans, searchCards } from '../api'

const props = defineProps({
  projectId: { type: [String, Number, null], default: null },
  showClose: { type: Boolean, default: true }
})

const emit = defineEmits(['close', 'select-card', 'select-detail'])

/** Promise.allSettled 中 axios 响应体 */
function settledBody(r) {
  if (!r || r.status !== 'fulfilled' || !r.value?.data) return null
  return r.value.data
}

function flattenPlans(nodes, acc = []) {
  for (const n of nodes || []) {
    if (n && typeof n === 'object') acc.push(n)
    if (n?.children?.length) flattenPlans(n.children, acc)
  }
  return acc
}

function textHaystack(obj, keys) {
  return keys
    .map((k) => obj?.[k])
    .filter((v) => v != null && String(v).trim() !== '')
    .map((v) => String(v).toLowerCase())
}

function entityMatchesQuery(item, query, extraKeys = []) {
  const chunks = textHaystack(item, ['title', 'name', 'description', ...extraKeys])
  return chunks.some((c) => c.includes(query))
}

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

      const qRaw = searchQuery.value.trim()

      // 并行：计划树、卡片全文搜索、三类独立实体列表（兼容历史表）
      const [plansRes, cardsSearchRes, badcasesRes, bugsRes, testcasesRes] = await Promise.allSettled([
        getProjectPlans(pid).catch(() => ({ data: {} })),
        searchCards({ query: qRaw, project_id: pid, per_page: 100, page: 1, types: 'bug,badcase,testcase' }).catch(
          () => ({ data: {} })
        ),
        getProjectBadcases(pid, 1, 300).catch(() => ({ data: {} })),
        getProjectBugs(pid, 1, 300).catch(() => ({ data: {} })),
        getProjectTestCases(pid, 1, 300).catch(() => ({ data: {} }))
      ])

      const results = []

      // 迭代计划：GET .../plans 返回 { success, plans: 树 }
      const plansBody = settledBody(plansRes)
      const planFlat = flattenPlans(plansBody?.plans || [])
      planFlat.forEach((item) => {
        if (entityMatchesQuery(item, query)) {
          results.push({
            type: 'plan',
            id: item.id,
            title: item.name || item.title || `Plan#${item.id}`,
            status: item.status || '',
            status_text: item.status_text || '',
            details: []
          })
        }
      })

      // 迭代卡片：后端 /api/cards/search（标题+描述 ilike）
      const cardSearchBody = settledBody(cardsSearchRes)
      const cardHits = cardSearchBody?.data?.results || cardSearchBody?.results || []
      cardHits.forEach((item) => {
        const gk = cardRowGroupKey(item.type)
        results.push({
          type: 'card',
          groupKey: gk,
          id: item.id,
          title: item.title,
          plan_id: item.plan_id,
          cardType: item.type,
          status: item.status || '',
          status_text: item.status_text || '',
          details: item.details || []
        })
      })

      // BadCase 实体表
      const badcases = settledBody(badcasesRes)?.badcases || []
      badcases.forEach((item) => {
        if (
          entityMatchesQuery(item, query, [
            'base_problem',
            'case_category',
            'reproduction_steps',
            'answer',
            'correct_answer'
          ])
        ) {
          results.push({
            type: 'badcase',
            groupKey: 'badcase',
            id: item.id,
            title: item.title,
            status: item.status || 'open',
            status_text: item.status_text || '',
            details: item.details || []
          })
        }
        if (item.details?.length) {
          const matchedDetails = item.details.filter(
            (d) =>
              (d.description || '').toLowerCase().includes(query) ||
              (d.title || '').toLowerCase().includes(query)
          )
          if (matchedDetails.length) {
            const alreadyAdded = results.some((r) => r.type === 'badcase' && String(r.id) === String(item.id))
            if (!alreadyAdded) {
              results.push({
                type: 'badcase',
                groupKey: 'badcase',
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

      // Bug 实体表（接口复用 badcases 键名）
      const bugs = settledBody(bugsRes)?.badcases || []
      bugs.forEach((item) => {
        if (entityMatchesQuery(item, query, ['description', 'bug_type'])) {
          results.push({
            type: 'bug',
            groupKey: 'bug',
            id: item.id,
            title: item.title,
            status: item.status || 'open',
            status_text: item.status_text || '',
            details: item.details || []
          })
        }
        if (item.details?.length) {
          const matchedDetails = item.details.filter(
            (d) =>
              (d.description || '').toLowerCase().includes(query) ||
              (d.title || '').toLowerCase().includes(query)
          )
          if (matchedDetails.length) {
            const alreadyAdded = results.some((r) => r.type === 'bug' && String(r.id) === String(item.id))
            if (!alreadyAdded) {
              results.push({
                type: 'bug',
                groupKey: 'bug',
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

      // 测试用例实体表
      const testcases = settledBody(testcasesRes)?.badcases || []
      testcases.forEach((item) => {
        if (entityMatchesQuery(item, query, ['case_type', 'remark'])) {
          results.push({
            type: 'testcase',
            groupKey: 'testcase',
            id: item.id,
            title: item.title,
            status: item.status || 'active',
            status_text: item.status_text || '',
            details: item.details || []
          })
        }
        if (item.details?.length) {
          const matchedDetails = item.details.filter(
            (d) =>
              (d.description || '').toLowerCase().includes(query) ||
              (d.title || '').toLowerCase().includes(query)
          )
          if (matchedDetails.length) {
            const alreadyAdded = results.some((r) => r.type === 'testcase' && String(r.id) === String(item.id))
            if (!alreadyAdded) {
              results.push({
                type: 'testcase',
                groupKey: 'testcase',
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
  const labels = {
    plan: '迭代计划',
    card: '其他卡片',
    bug: 'Bug',
    badcase: 'BadCase',
    testcase: '测试用例'
  }
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
