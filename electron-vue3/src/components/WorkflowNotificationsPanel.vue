<template>
  <div class="wnp-root">
    <header class="wnp-header">
      <h1 class="wnp-title">{{ t('notifInbox.pageTitle') }}</h1>
      <p class="wnp-hint">{{ t('notifInbox.hint') }}</p>
      <div class="wnp-toolbar">
        <div class="wnp-search-wrap">
          <span class="wnp-search-icon" aria-hidden="true">⌕</span>
          <input
            v-model="searchInput"
            type="search"
            class="wnp-search"
            :placeholder="t('notifInbox.searchPlaceholder')"
            autocomplete="off"
            @keyup.enter="applySearch"
          />
          <button type="button" class="wnp-btn" @click="applySearch">{{ t('common.search') }}</button>
        </div>
        <select v-model="entityFilter" class="wnp-select" @change="reload">
          <option value="">{{ t('notifInbox.entityAll') }}</option>
          <option value="badcase">BadCase</option>
          <option value="bug">Bug</option>
          <option value="testcase">TestCase</option>
        </select>
        <label class="wnp-check">
          <input v-model="unreadOnly" type="checkbox" @change="reload" />
          {{ t('notifInbox.unreadOnly') }}
        </label>
        <button type="button" class="wnp-btn primary" :disabled="markAllLoading" @click="markAllRead">
          {{ t('notifInbox.markAllRead') }}
        </button>
      </div>
    </header>
    <div class="wnp-body">
      <p v-if="loading" class="wnp-muted">{{ t('common.loading') }}</p>
      <p v-else-if="errorMsg" class="wnp-error">{{ errorMsg }}</p>
      <p v-else-if="!items.length" class="wnp-muted">{{ t('notifInbox.empty') }}</p>
      <table v-else class="wnp-table">
        <thead>
          <tr>
            <th>{{ t('notifInbox.colTime') }}</th>
            <th>{{ t('notifInbox.colType') }}</th>
            <th>{{ t('notifInbox.colEvent') }}</th>
            <th>{{ t('notifInbox.colTitle') }}</th>
            <th>{{ t('notifInbox.colProject') }}</th>
            <th>{{ t('notifInbox.colActor') }}</th>
            <th>{{ t('notifInbox.colStatus') }}</th>
            <th>{{ t('notifInbox.colRead') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in items"
            :key="row.id"
            :class="{ unread: !row.read_at }"
            @click="onRowClick(row)"
          >
            <td class="wnp-nowrap">{{ formatTime(row.created_at) }}</td>
            <td><span class="wnp-badge">{{ row.entity_type }}</span> #{{ row.entity_id }}</td>
            <td>{{ row.event }}</td>
            <td class="wnp-title-cell">{{ row.title || '—' }}</td>
            <td>{{ row.project_name || '—' }}</td>
            <td>{{ row.actor_name || '—' }}</td>
            <td class="wnp-small">
              <template v-if="row.previous_status">{{ row.previous_status }} → </template>{{ row.status || '—' }}
            </td>
            <td>{{ row.read_at ? t('notifInbox.read') : t('notifInbox.unread') }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="pagination.total > pagination.per_page" class="wnp-pager">
        <button type="button" class="wnp-btn" :disabled="pagination.page <= 1 || loading" @click="goPage(pagination.page - 1)">
          {{ t('common.prev') }}
        </button>
        <span class="wnp-pageinfo">{{ pagination.page }} / {{ pagination.pages || 1 }} · {{ pagination.total }}</span>
        <button
          type="button"
          class="wnp-btn"
          :disabled="!pagination.has_next || loading"
          @click="goPage(pagination.page + 1)"
        >
          {{ t('common.next') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  getWorkflowNotifications,
  markWorkflowNotificationRead,
  markAllWorkflowNotificationsRead
} from '../api.js'

const props = defineProps({
  projectId: { type: [String, Number], default: null },
  visible: { type: Boolean, default: true }
})

const { t } = useI18n()

const loading = ref(false)
const markAllLoading = ref(false)
const errorMsg = ref('')
const items = ref([])
const searchInput = ref('')
const appliedSearch = ref('')
const entityFilter = ref('')
const unreadOnly = ref(false)
const pagination = ref({
  page: 1,
  per_page: 20,
  total: 0,
  pages: 1,
  has_next: false,
  has_prev: false
})

const formatTime = (iso) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const buildParams = (page = 1) => {
  const p = { page, per_page: pagination.value.per_page }
  const pid = props.projectId
  if (pid != null && pid !== '' && !Number.isNaN(Number(pid))) {
    p.project_id = Number(pid)
  }
  if (appliedSearch.value.trim()) p.q = appliedSearch.value.trim()
  if (entityFilter.value) p.entity_type = entityFilter.value
  if (unreadOnly.value) p.unread_only = 'true'
  return p
}

const reload = async (page = 1) => {
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await getWorkflowNotifications(buildParams(page))
    if (!data?.success) {
      errorMsg.value = data?.error || t('notifInbox.loadError')
      items.value = []
      return
    }
    items.value = data.items || []
    pagination.value = {
      page: data.pagination?.page || page,
      per_page: data.pagination?.per_page || 20,
      total: data.pagination?.total || 0,
      pages: data.pagination?.pages || 1,
      has_next: !!data.pagination?.has_next,
      has_prev: !!data.pagination?.has_prev
    }
  } catch (e) {
    errorMsg.value = e?.response?.data?.error || e?.message || t('notifInbox.loadError')
    items.value = []
  } finally {
    loading.value = false
  }
}

const applySearch = () => {
  appliedSearch.value = searchInput.value
  reload(1)
}

const goPage = (p) => {
  if (p < 1) return
  reload(p)
}

const onRowClick = async (row) => {
  if (row.read_at) return
  try {
    await markWorkflowNotificationRead(row.id)
    row.read_at = new Date().toISOString()
  } catch {
    /* ignore */
  }
}

const markAllRead = async () => {
  markAllLoading.value = true
  try {
    const params = {}
    const pid = props.projectId
    if (pid != null && pid !== '' && !Number.isNaN(Number(pid))) {
      params.project_id = Number(pid)
    }
    await markAllWorkflowNotificationsRead(params)
    await reload(pagination.value.page)
  } catch {
    /* ignore */
  } finally {
    markAllLoading.value = false
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) reload(1)
  }
)

watch(
  () => props.projectId,
  () => {
    if (props.visible) reload(1)
  }
)

onMounted(() => {
  if (props.visible) reload(1)
})
</script>

<style scoped>
.wnp-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
  border-top: 1px solid #e9ecef;
}
.wnp-header {
  flex-shrink: 0;
  padding: 16px 20px 12px;
  border-bottom: 1px solid #e9ecef;
}
.wnp-title {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 600;
  color: #1a1a2e;
}
.wnp-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #6c757d;
}
.wnp-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.wnp-search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 200px;
  max-width: 520px;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  padding: 4px 8px;
  background: #f8f9fa;
}
.wnp-search-icon {
  color: #868e96;
  font-size: 14px;
}
.wnp-search {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  min-width: 0;
}
.wnp-select {
  height: 34px;
  border-radius: 8px;
  border: 1px solid #dee2e6;
  padding: 0 8px;
  font-size: 13px;
}
.wnp-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #495057;
  user-select: none;
}
.wnp-btn {
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #ced4da;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
}
.wnp-btn:hover:not(:disabled) {
  background: #f1f3f5;
}
.wnp-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.wnp-btn.primary {
  background: #4263eb;
  border-color: #4263eb;
  color: #fff;
}
.wnp-btn.primary:hover:not(:disabled) {
  background: #364fc7;
  border-color: #364fc7;
}
.wnp-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 16px 20px;
}
.wnp-muted {
  color: #868e96;
  font-size: 14px;
}
.wnp-error {
  color: #c92a2a;
  font-size: 14px;
}
.wnp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.wnp-table th,
.wnp-table td {
  border-bottom: 1px solid #e9ecef;
  padding: 10px 8px;
  text-align: left;
  vertical-align: top;
}
.wnp-table th {
  color: #495057;
  font-weight: 600;
  background: #f8f9fa;
  position: sticky;
  top: 0;
  z-index: 1;
}
.wnp-table tbody tr {
  cursor: pointer;
}
.wnp-table tbody tr:hover {
  background: #f1f3f5;
}
.wnp-table tbody tr.unread {
  background: #e7f5ff;
}
.wnp-nowrap {
  white-space: nowrap;
}
.wnp-title-cell {
  max-width: 280px;
  word-break: break-word;
}
.wnp-small {
  font-size: 12px;
  color: #495057;
}
.wnp-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  background: #e7f5ff;
  color: #1864ab;
  font-weight: 500;
}
.wnp-pager {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}
.wnp-pageinfo {
  font-size: 13px;
  color: #495057;
}
</style>
