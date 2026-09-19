<template>
  <div class="reports-panel">
    <div class="reports-panel-header">
      <span class="reports-panel-title">📊 {{ t('reportsPanel.title') }}</span>
      <button
        type="button"
        class="reports-refresh-btn"
        :class="{ spinning: loading }"
        :title="t('reportsPanel.refresh')"
        :disabled="loading"
        @click="reload"
      >
        ⟳
      </button>
    </div>

    <div v-if="loading && !sessions.length" class="reports-state">
      {{ t('reportsPanel.loading') }}
    </div>
    <div v-else-if="loadError" class="reports-state reports-state--error">
      {{ t('reportsPanel.loadFail') }}
    </div>
    <div v-else-if="!sessions.length" class="reports-state">
      {{ t('reportsPanel.empty') }}
    </div>

    <div v-else class="reports-sessions">
      <div v-for="s in sessions" :key="s.key" class="reports-session">
        <div class="reports-session-head" @click="toggleSession(s.key)">
          <span class="reports-session-caret" :class="{ open: isExpanded(s.key) }">▸</span>
          <span class="reports-session-title" :title="sessionTitle(s)">{{ sessionTitle(s) }}</span>
          <span class="reports-session-count">{{ t('reportsPanel.runCount', { n: s.run_count }) }}</span>
          <span class="reports-status-chip" :class="statusClass(s.latest_status)">
            {{ statusLabel(s.latest_status) }}
          </span>
        </div>

        <div v-show="isExpanded(s.key)" class="reports-run-list">
          <div
            v-for="r in s.runs"
            :key="r.kind + ':' + r.id"
            class="reports-run-row"
            :class="{ active: String(r.id) === String(activeKey) }"
            :title="r.title"
            @click="emitOpen(r)"
          >
            <span class="reports-run-kind">{{ r.kind === 'cdp_test' ? '🧪' : '🤖' }}</span>
            <div class="reports-run-main">
              <div class="reports-run-title">{{ r.title || kindLabel(r.kind) }}</div>
              <div class="reports-run-meta">
                <span class="reports-run-status" :class="statusClass(r.status)">
                  {{ statusLabel(r.status) }}
                </span>
                <span v-if="r.kind === 'cdp_test'" class="reports-run-counts">
                  {{ t('reportsPanel.passFail', { pass: r.pass_count ?? 0, fail: r.fail_count ?? 0 }) }}
                </span>
                <span class="reports-run-time">{{ fmtTime(r.created_at) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { listReports } from '../../api.js'
import { reportStatusClass, reportStatusLabel } from '../../utils/reportStatus.js'

const props = defineProps({
  projectId: { type: [String, Number, null], default: null },
  /** 当前打开的报告实体 id：用于高亮跟随（打开报告 Tab 时左侧自动指向对应条目） */
  activeKey: { type: String, default: '' }
})

const emit = defineEmits(['openReport'])

const { t } = useI18n()

const sessions = ref([])
const loading = ref(false)
const loadError = ref(false)
const expandedKeys = ref([])

const fetchList = async () => {
  if (props.projectId == null || props.projectId === '') return
  loading.value = true
  loadError.value = false
  try {
    const res = await listReports(props.projectId)
    const data = res?.data || {}
    if (data.success) {
      sessions.value = Array.isArray(data.sessions) ? data.sessions : []
    } else {
      loadError.value = true
    }
  } catch (e) {
    console.warn('[ReportsPanel] 加载报告列表失败:', e)
    loadError.value = true
  } finally {
    loading.value = false
  }
}

const reload = () => {
  void fetchList()
}

onMounted(fetchList)
watch(() => props.projectId, () => {
  sessions.value = []
  expandedKeys.value = []
  void fetchList()
})

const isExpanded = (key) => expandedKeys.value.includes(key)
const toggleSession = (key) => {
  const i = expandedKeys.value.indexOf(key)
  if (i >= 0) expandedKeys.value.splice(i, 1)
  else expandedKeys.value.push(key)
}

const sessionTitle = (s) => {
  if (s.title && String(s.title).trim()) return String(s.title)
  return t('reportsPanel.noSessionTitle')
}

const emitOpen = (r) => {
  emit('openReport', { kind: r.kind, id: r.id, title: r.title || '' })
}

const kindLabel = (kind) =>
  kind === 'cdp_test' ? t('reportsPanel.kindCdp') : t('reportsPanel.kindAgentRun')

/** 状态展示：cdp 与 react run 的枚举合流（见 utils/reportStatus.js） */
const statusLabel = (st) => reportStatusLabel(t, st)
const statusClass = reportStatusClass

const pad2 = (n) => String(n).padStart(2, '0')
const fmtTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** 跟随：打开某份报告时自动展开其所在会话组 */
watch(
  () => props.activeKey,
  (k) => {
    if (!k) return
    for (const s of sessions.value) {
      if ((s.runs || []).some((r) => String(r.id) === String(k))) {
        if (!isExpanded(s.key)) expandedKeys.value.push(s.key)
        break
      }
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.reports-panel {
  height: 100%;
  padding: 12px;
  overflow-y: auto;
  min-width: 0;
  box-sizing: border-box;
}

.reports-panel-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}

.reports-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reports-refresh-btn {
  border: none;
  background: transparent;
  border-radius: 4px;
  width: 24px;
  height: 24px;
  cursor: pointer;
  color: #666;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.15s;
}

.reports-refresh-btn:hover {
  background: #eef2f7;
}

.reports-refresh-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.reports-refresh-btn.spinning {
  animation: reports-spin 0.8s linear infinite;
}

@keyframes reports-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.reports-state {
  padding: 14px 4px;
  color: #888;
  font-size: 12px;
}

.reports-state--error {
  color: #c0392b;
}

.reports-sessions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reports-session {
  border: 1px solid #ececec;
  border-radius: 6px;
  background: #fff;
  overflow: hidden;
}

.reports-session-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  cursor: pointer;
  user-select: none;
}

.reports-session-head:hover {
  background: #f6f8fb;
}

.reports-session-caret {
  color: #999;
  font-size: 10px;
  transition: transform 0.15s;
  flex-shrink: 0;
}

.reports-session-caret.open {
  transform: rotate(90deg);
}

.reports-session-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 600;
  color: #444;
}

.reports-session-count {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
}

.reports-status-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  flex-shrink: 0;
  background: #f0f0f0;
  color: #777;
}

.reports-run-list {
  border-top: 1px solid #f0f0f0;
  padding: 2px 0;
}

.reports-run-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 8px 6px 14px;
  cursor: pointer;
}

.reports-run-row:hover {
  background: #f6f8fb;
}

.reports-run-row.active {
  background: #e8f1fd;
}

.reports-run-kind {
  font-size: 12px;
  flex-shrink: 0;
  line-height: 16px;
}

.reports-run-main {
  flex: 1;
  min-width: 0;
}

.reports-run-title {
  font-size: 12px;
  color: #444;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reports-run-row.active .reports-run-title {
  color: #1a73e8;
}

.reports-run-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 11px;
  color: #999;
}

.reports-run-status {
  flex-shrink: 0;
}

.reports-run-counts {
  flex-shrink: 0;
}

.reports-run-time {
  margin-left: auto;
  flex-shrink: 0;
}

/* 状态色：chip 与行内文字共用 */
.st-running { color: #1a73e8; }
.reports-status-chip.st-running { background: #e8f1fd; color: #1a73e8; }
.st-passed { color: #2e7d32; }
.reports-status-chip.st-passed { background: #e6f4ea; color: #2e7d32; }
.st-completed { color: #2e7d32; }
.reports-status-chip.st-completed { background: #e6f4ea; color: #2e7d32; }
.st-failed { color: #c0392b; }
.reports-status-chip.st-failed { background: #fdecea; color: #c0392b; }
.st-partial { color: #b26a00; }
.reports-status-chip.st-partial { background: #fff4e5; color: #b26a00; }
.st-blocked { color: #8a8a8a; }
.reports-status-chip.st-blocked { background: #f0f0f0; color: #8a8a8a; }
.st-cancelled { color: #8a8a8a; }
.reports-status-chip.st-cancelled { background: #f0f0f0; color: #8a8a8a; }
.st-unknown { color: #8a8a8a; }
</style>
